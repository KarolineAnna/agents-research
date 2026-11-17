"""Núcleo reutilizável de agente com ferramentas (tool calling), independente do provedor de IA.

Um agente = instruções + ferramentas (funções Python) + um validador da resposta final.
O laço:
  1. manda a conversa ao modelo; ele responde com chamadas de ferramenta ou com o texto final;
  2. executa as ferramentas pedidas e devolve os resultados (truncados, para caber no contexto);
  3. repete até o texto final, respeitando limites de passos, de tempo e de correções;
  4. o texto final passa pelo validador; se reprovar, volta ao modelo com a lista de problemas.

Garantias de robustez:
  - troca de provedor no meio da conversa quando um falha (limite gratuito, rede, erro);
  - chamadas repetidas com os mesmos argumentos reaproveitam o resultado (sem custo e sem loop);
  - exceções dentro de uma ferramenta viram {"erro": ...} para o modelo, nunca derrubam o laço;
  - argumentos JSON inválidos e ferramentas inexistentes são devolvidos como erro ao modelo;
  - orçamento de tempo total e de passos; ao estourar, o modelo é instruído a concluir;
  - registro de cada passo (ferramenta, argumentos, duração, resumo) para auditoria na tela;
  - tempo de cada chamada à IA (provedor, segundos, sucesso) nas métricas, para saber onde a demora está;
  - quando o modelo empaca no mesmo erro do validador, ``podar=True`` tira só as frases reprovadas
    (cada uma conferida sozinha) e aceita o resto se ele passar inteiro no validador.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from indicadores_b3.agents import llm

log = logging.getLogger(__name__)


@dataclass
class Ferramenta:
    nome: str
    descricao: str
    funcao: Callable[..., dict]
    parametros: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    resumo: Callable[[dict], str] | None = None  # texto curto para o registro

    def esquema(self) -> dict:
        return {"type": "function", "function": {"name": self.nome, "description": self.descricao, "parameters": self.parametros}}


@dataclass
class Resultado:
    texto: str | None
    passos: list[dict]
    provedores: list[str]
    metricas: dict

    def to_dict(self) -> dict:
        return {"texto": self.texto, "passos": self.passos, "provedores": self.provedores, "metricas": self.metricas}


class AgenteFerramentas:
    def __init__(self, sistema: str, ferramentas: list[Ferramenta], validar: Callable[[str], list[str]] | None = None,
                 max_passos: int = 14, max_correcoes: int = 2, orcamento_s: float = 300, max_chars_resultado: int = 16000,
                 exigir_ferramenta: bool = True, provedores: list[tuple[str, str]] | None = None, podar: bool = False):
        self.sistema = sistema
        self.ferramentas = {f.nome: f for f in ferramentas}
        self.validar = validar
        self.max_passos, self.max_correcoes = max_passos, max_correcoes
        self.orcamento_s, self.max_chars = orcamento_s, max_chars_resultado
        self.exigir_ferramenta = exigir_ferramenta
        self._provs = provedores
        self.podar = podar
        self.ia: list[dict] = []  # uma linha por chamada ao modelo
        self.passos: list[dict] = []
        self._memo: dict[str, dict] = {}

    # ---------- execução de uma ferramenta ----------
    def _executar(self, nome: str, args_txt: str | None) -> tuple[dict, dict]:
        f = self.ferramentas.get(nome)
        if not f:
            return {"erro": f"ferramenta desconhecida: {nome}. Disponíveis: {', '.join(self.ferramentas)}"}, {}
        try:
            args = json.loads(args_txt or "{}") or {}
            if not isinstance(args, dict):
                raise ValueError("argumentos precisam ser um objeto JSON")
        except ValueError as e:
            return {"erro": f"argumentos inválidos ({e}). Envie JSON no formato do esquema."}, {}
        chave = nome + json.dumps(args, sort_keys=True, ensure_ascii=False)
        if chave in self._memo:
            return {**self._memo[chave], "_aviso": "mesma chamada já feita; resultado reaproveitado"}, args
        try:
            r = f.funcao(**args)
        except TypeError as e:
            r = {"erro": f"argumentos inválidos: {e}"}
        except Exception as e:  # noqa: BLE001 — erro da ferramenta vira informação para o modelo
            log.exception("ferramenta %s falhou", nome)
            r = {"erro": f"{type(e).__name__}: {e}"[:400]}
        if not isinstance(r, dict):
            r = {"resultado": r}
        if "erro" not in r:
            self._memo[chave] = r
        return r, args

    def _serializar(self, r: dict) -> str:
        txt = json.dumps(r, ensure_ascii=False, default=str)
        if len(txt) > self.max_chars:
            txt = txt[: self.max_chars] + '…" [resultado truncado: peça detalhes com outra ferramenta]'
        return txt

    # ---------- laço ----------
    def rodar(self, pedido: str) -> Resultado:
        provs = self._provs if self._provs is not None else llm.disponiveis()
        if not provs:
            raise llm.ErroProvedor("Nenhum provedor de IA configurado: informe a chave gratuita do Gemini ou do Groq, ou rode o Ollama.",
                                   transitorio=False)
        msgs = [{"role": "system", "content": self.sistema}, {"role": "user", "content": pedido}]
        esquemas = [f.esquema() for f in self.ferramentas.values()]
        t_ini, i_prov, correcoes, usados, ultimos_problemas = time.time(), 0, 0, [], None
        uso = {"prompt_tokens": 0, "completion_tokens": 0}
        n_ferr, cobrou_ferramenta, texto, fim_forcado = 0, False, None, False

        for _ in range(self.max_passos + self.max_correcoes + 6):
            p, modelo = provs[i_prov]
            t_ia = time.time()
            try:
                resp = llm.conversar(p, modelo, msgs, [] if fim_forcado else esquemas)
            except llm.ErroProvedor as e:
                dt = round(time.time() - t_ia, 1)
                self.ia.append({"provedor": f"{p} · {modelo}", "segundos": dt, "ok": False})
                self.passos.append({"tipo": "erro", "texto": f"{e} ({dt:.0f} s perdidos)"})
                i_prov += 1
                if i_prov >= len(provs):
                    break
                self.passos.append({"tipo": "info", "texto": f"Trocando para {provs[i_prov][0]} ({provs[i_prov][1]})."})
                continue
            self.ia.append({"provedor": f"{p} · {modelo}", "segundos": round(time.time() - t_ia, 1), "ok": True})
            if (p, modelo) not in usados:
                usados.append((p, modelo))
            for k in uso:
                uso[k] += int((resp.get("_uso") or {}).get(k) or 0)
            chamadas = resp.get("tool_calls") or []
            conteudo = (resp.get("content") or "").strip()
            msgs.append({"role": "assistant", "content": conteudo, **({"tool_calls": chamadas} if chamadas else {})})

            if chamadas:
                if conteudo:
                    self.passos.append({"tipo": "pensamento", "texto": conteudo[:1200]})
                for c in chamadas:
                    nome = (c.get("function") or {}).get("name", "?")
                    t0 = time.time()
                    r, args = self._executar(nome, (c.get("function") or {}).get("arguments"))
                    n_ferr += 1
                    f = self.ferramentas.get(nome)
                    resumo = r.get("erro") or (f.resumo(r) if f and f.resumo else None) or r.get("_aviso") or "ok"
                    self.passos.append({"tipo": "ferramenta", "nome": nome, "args": args, "segundos": round(time.time() - t0, 1),
                                        "resumo": resumo if "_aviso" not in r else f"{resumo} (reaproveitado)"})
                    msgs.append({"role": "tool", "tool_call_id": c.get("id") or nome, "name": nome, "content": self._serializar(r)})
                estourou = n_ferr >= self.max_passos or time.time() - t_ini > self.orcamento_s
                if estourou and not fim_forcado:
                    fim_forcado = True
                    self.passos.append({"tipo": "info", "texto": "Limite de passos ou de tempo atingido: pedindo a conclusão."})
                    msgs.append({"role": "user", "content": "Limite atingido. Escreva agora a resposta final com o que já tem, sem chamar ferramentas."})
                continue

            # resposta sem ferramentas = candidata a final
            if self.exigir_ferramenta and n_ferr == 0 and not cobrou_ferramenta:
                cobrou_ferramenta = True
                self.passos.append({"tipo": "info", "texto": "O modelo respondeu sem investigar; pedindo que use as ferramentas."})
                msgs.append({"role": "user", "content": "Você ainda não usou nenhuma ferramenta. Investigue com as ferramentas antes de responder."})
                continue
            problemas = self.validar(conteudo) if (self.validar and conteudo) else ([] if conteudo else ["resposta vazia"])
            self.passos.append({"tipo": "rascunho", "texto": f"Resposta escrita ({len(conteudo)} caracteres); problemas: "
                                                             f"{', '.join(problemas) if problemas else 'nenhum'}."})
            if not problemas:
                texto = conteudo
                break
            # empacou (mesmo erro de novo) ou acabaram as correções: tenta salvar o texto tirando só as frases reprovadas
            if self.podar and self.validar and (problemas == ultimos_problemas or correcoes >= self.max_correcoes):
                podado, tiradas = podar_frases(conteudo, self.validar)
                if tiradas and len(podado) >= 0.5 * len(conteudo) and not self.validar(podado):
                    self.passos.append({"tipo": "info", "texto": f"O modelo repetiu o mesmo erro; {len(tiradas)} frase(s) com números não "
                                                                 f"conferidos foram retiradas e o restante foi aprovado: " + " | ".join(t[:140] for t in tiradas)})
                    texto = podado
                    break
            ultimos_problemas = problemas
            if correcoes >= self.max_correcoes:
                self.passos.append({"tipo": "erro", "texto": "A resposta continuou reprovada pelo validador: descartada."})
                break
            correcoes += 1
            msgs.append({"role": "user", "content": "A resposta foi reprovada pelo validador: " + "; ".join(problemas) +
                         ". Reescreva a resposta completa corrigindo isso."})

        metricas = {"segundos": round(time.time() - t_ini, 1), "chamadas_ferramenta": n_ferr, "correcoes": correcoes,
                    "tokens": uso, "concluiu": texto is not None,
                    "segundos_ia": round(sum(x["segundos"] for x in self.ia), 1),
                    "segundos_ferramentas": round(sum(x.get("segundos", 0) for x in self.passos if x["tipo"] == "ferramenta"), 1),
                    "chamadas_ia": self.ia}
        log.info("agente concluiu=%s em %.1fs, %d ferramentas", texto is not None, metricas["segundos"], n_ferr)
        return Resultado(texto, self.passos, [f"{p} · {m}" for p, m in usados], metricas)


FRASE = re.compile(r"(?<=[.!?;])\s+")


def podar_frases(texto: str, validar: Callable[[str], list[str]]) -> tuple[str, list[str]]:
    """Tira as frases que o validador reprova quando conferidas sozinhas. Títulos e a estrutura de linhas ficam.
    Devolve (texto podado, frases retiradas)."""
    tiradas, linhas = [], []
    for linha in texto.split("\n"):
        if not linha.strip() or linha.lstrip().startswith("#"):
            linhas.append(linha)
            continue
        recuo = re.match(r"\s*(?:[-*]|\d+\.)?\s*", linha).group(0)
        frases = FRASE.split(linha[len(recuo):])
        boas = []
        for f in frases:
            if f.strip() and validar(f):
                tiradas.append(f.strip())
            else:
                boas.append(f)
        if any(b.strip() for b in boas):
            linhas.append(recuo + " ".join(b for b in boas if b.strip()))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip(), tiradas

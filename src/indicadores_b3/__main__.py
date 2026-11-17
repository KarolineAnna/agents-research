"""Inicia o site local: ``python -m indicadores_b3`` (ou o comando ``indicadores-b3``)."""
import uvicorn

from indicadores_b3 import config


def main() -> None:
    config.garantir_pastas()
    print(f"Indicadores B3 em http://{config.HOST}:{config.PORTA}")
    uvicorn.run("indicadores_b3.api.app:app", host=config.HOST, port=config.PORTA)


if __name__ == "__main__":
    main()

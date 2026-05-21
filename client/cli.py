"""CLI del Mini-DFS — apunta SOLO al NameNode (IP pública).

Uso:
    python client/cli.py --url http://<namenode>:8000 login -u demo -p demo123
    python client/cli.py mkdir /datos
    python client/cli.py put pelicula.bin /datos/pelicula.bin
    python client/cli.py ls /datos
    python client/cli.py get /datos/pelicula.bin ./descarga.bin
    python client/cli.py rm /datos/pelicula.bin
    python client/cli.py rmdir /datos

La URL y el token se guardan en ~/.dfs_config tras el login.
"""

import json
import os
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dfs_client import DfsClient, DfsError  # noqa: E402

CONFIG_PATH = Path.home() / ".dfs_config"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _progress(done: int, total: int) -> None:
    click.echo(f"  bloque {done}/{total}", err=True)


@click.group()
@click.option("--url", default=None, help="URL del NameNode (ej. http://1.2.3.4:8000)")
@click.pass_context
def cli(ctx, url):
    cfg = _load_config()
    base = url or cfg.get("namenode_url") or os.getenv("DFS_NAMENODE_URL", "http://localhost:8000")
    client = DfsClient(base_url=base, token=cfg.get("token"))
    ctx.obj = {"client": client, "cfg": cfg}


def _run(fn):
    try:
        return fn()
    except DfsError as exc:
        raise click.ClickException(str(exc))


@cli.command()
@click.option("-u", "--username", required=True)
@click.option("-p", "--password", required=True)
@click.pass_obj
def login(obj, username, password):
    """Autentica y guarda el token en ~/.dfs_config."""
    client = obj["client"]
    _run(lambda: client.login(username, password))
    cfg = obj["cfg"]
    cfg["namenode_url"] = client.base_url
    cfg["token"] = client.token
    _save_config(cfg)
    click.echo(f"Login OK en {client.base_url}; token guardado en {CONFIG_PATH}")


@cli.command()
@click.argument("path")
@click.pass_obj
def mkdir(obj, path):
    """Crea un directorio."""
    res = _run(lambda: obj["client"].mkdir(path))
    click.echo(f"Directorio creado: {res['created']}")


@cli.command()
@click.argument("path", default="/")
@click.pass_obj
def ls(obj, path):
    """Lista el contenido de un directorio."""
    entries = _run(lambda: obj["client"].ls(path))
    if not entries:
        click.echo("(vacío)")
        return
    for e in entries:
        tag = "d" if e["is_directory"] else "-"
        click.echo(f"{tag}  {e['size_bytes']:>12}  {e['path']}")


@cli.command()
@click.argument("local")
@click.argument("remote")
@click.pass_obj
def put(obj, local, remote):
    """Sube un archivo local al DFS (fragmenta, distribuye y replica)."""
    res = _run(lambda: obj["client"].put(local, remote, progress=_progress))
    click.echo(f"Subido: {res['path']} ({res['size_bytes']} bytes, {res['blocks']} bloques)")


@cli.command()
@click.argument("remote")
@click.argument("local")
@click.pass_obj
def get(obj, remote, local):
    """Descarga y reconstruye un archivo del DFS."""
    res = _run(lambda: obj["client"].get(remote, local, progress=_progress))
    click.echo(f"Descargado: {res['path']} -> {res['local']} ({res['blocks']} bloques)")


@cli.command()
@click.argument("path")
@click.pass_obj
def rm(obj, path):
    """Elimina un archivo y sus bloques."""
    res = _run(lambda: obj["client"].rm(path))
    click.echo(f"Eliminado: {res['deleted']}")


@cli.command()
@click.argument("path")
@click.pass_obj
def rmdir(obj, path):
    """Elimina un directorio vacío."""
    res = _run(lambda: obj["client"].rmdir(path))
    click.echo(f"Directorio eliminado: {res['deleted']}")


if __name__ == "__main__":
    cli()

"""Sincronização com o Banco de Receitas no Notion (API oficial, data sources).

Regras:
- Busca a linha pela coluna "Receita"; se não existir, cria.
- Em linha existente, só preenche campos VAZIOS (não sobrescreve o que a equipe escreveu à mão).
  Exceções: "Origem do vídeo" vira "Gravado por nós" e "Status" sobe para "Editado"
  quando ainda está em Ideia/Texto pronto.
- Nunca toca em "Vídeo editado", datas ou métricas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

API = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"
TITLE_PROP = "Receita"
STATUS_UPGRADABLE = {"", "Ideia", "Texto pronto"}
ORIGEM_REFERENCIA = "Referência (não postar)"

# Campos que a ferramenta gera e que o --regenerar pode sobrescrever (nunca Vídeo editado, Estilo, métricas, Origem).
REGENERABLE = {
    "Gancho A (curiosidade)", "Gancho B (benefício)", "Gancho C (erro comum)", "Gancho",
    "Título do pin", "Descrição", "CTA", "Roteiro de locução", "No e-book",
    "Link do pin", "Link B", "Link C", "Link capa", "Link colagem",
}

# Campos de texto que a ferramenta gera e que, se já preenchidos no Notion, prevalecem no vídeo.
TEXT_FIELDS = [
    "Gancho A (curiosidade)", "Gancho B (benefício)", "Gancho C (erro comum)", "Gancho",
    "Título do pin", "Descrição", "CTA", "Roteiro de locução",
]


class NotionError(RuntimeError):
    pass


@dataclass
class NotionRow:
    page_id: str
    values: dict[str, object] = field(default_factory=dict)  # nome do campo -> valor simples

    def get(self, name: str):
        return self.values.get(name)


def _plain(prop: dict):
    """Converte uma propriedade do Notion num valor simples (str/bool/float/None)."""
    t = prop.get("type")
    if t in ("title", "rich_text"):
        return "".join(part.get("plain_text", "") for part in prop.get(t, []))
    if t == "select":
        return (prop.get("select") or {}).get("name", "")
    if t == "status":
        return (prop.get("status") or {}).get("name", "")
    if t in ("url", "number", "checkbox"):
        return prop.get(t)
    return None


def _is_empty(value) -> bool:
    return value in (None, "", False)


class NotionClient:
    def __init__(self, token: str, data_source_id: str):
        self.data_source_id = data_source_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        })
        self.schema: dict[str, dict] = {}
        self.rows: dict[str, NotionRow] = {}  # chave: nome da receita normalizado

    # ------------------------------------------------------------------ HTTP
    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self.session.request(method, f"{API}{path}", timeout=30, **kwargs)
        if resp.status_code == 401:
            raise NotionError("NOTION_TOKEN inválido")
        if resp.status_code == 404:
            raise NotionError("Banco de Receitas não encontrado. Confira NOTION_DATA_SOURCE_ID e se a "
                              "integração foi conectada ao banco (••• → Conexões no Notion)")
        if not resp.ok:
            raise NotionError(f"Notion {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    # ------------------------------------------------------------------ leitura
    def load(self) -> None:
        """Carrega o esquema (tipos e opções) e todas as linhas do banco."""
        ds = self._request("GET", f"/data_sources/{self.data_source_id}")
        self.schema = ds.get("properties", {})

        self.rows.clear()
        payload: dict = {"page_size": 100}
        while True:
            data = self._request("POST", f"/data_sources/{self.data_source_id}/query", json=payload)
            for page in data.get("results", []):
                values = {name: _plain(prop) for name, prop in page.get("properties", {}).items()}
                title = (values.get(TITLE_PROP) or "").strip()
                if title:
                    self.rows[title.casefold()] = NotionRow(page["id"], values)
            if not data.get("has_more"):
                break
            payload["start_cursor"] = data["next_cursor"]

    def options(self, prop_name: str) -> list[str]:
        prop = self.schema.get(prop_name, {})
        t = prop.get("type")
        return [o["name"] for o in (prop.get(t) or {}).get("options", [])] if t in ("select", "status") else []

    @property
    def recipe_names(self) -> list[str]:
        return [row.get(TITLE_PROP) for row in self.rows.values()]

    def find(self, recipe_name: str) -> NotionRow | None:
        return self.rows.get(recipe_name.strip().casefold())

    # ------------------------------------------------------------------ escrita
    def _encode(self, name: str, value) -> dict | None:
        t = self.schema.get(name, {}).get("type")
        if t == "title":
            return {"title": [{"text": {"content": str(value)[:2000]}}]}
        if t == "rich_text":
            return {"rich_text": [{"text": {"content": str(value)[:2000]}}]}
        if t == "select":
            return {"select": {"name": str(value)}}
        if t == "status":
            return {"status": {"name": str(value)}}
        if t == "url":
            return {"url": str(value)}
        if t == "checkbox":
            return {"checkbox": bool(value)}
        return None  # campo inexistente ou tipo não suportado: ignora

    def upsert(self, recipe_name: str, fields: dict[str, object], dry_run: bool = False,
               regenerate: bool = False) -> tuple[str, dict[str, object]]:
        """Cria ou completa a linha da receita.

        Retorna (acao, campos_escritos). Com dry_run=True nada é enviado ao Notion: só calcula o que seria
        escrito. Com regenerate=True, os campos gerados (REGENERABLE) são sobrescritos mesmo se preenchidos.
        Linha marcada como "Referência (não postar)" nunca tem Origem nem Status alterados.
        """
        row = self.find(recipe_name)
        props: dict[str, dict] = {}
        written: dict[str, object] = {}

        if row is None:
            for name, value in {TITLE_PROP: recipe_name, **fields}.items():
                if not _is_empty(value) and (enc := self._encode(name, value)):
                    props[name] = enc
                    written[name] = value
            if dry_run:
                return "seria criada", written
            page = self._request("POST", "/pages", json={
                "parent": {"type": "data_source_id", "data_source_id": self.data_source_id},
                "properties": props,
            })
            self.rows[recipe_name.strip().casefold()] = NotionRow(page["id"], {TITLE_PROP: recipe_name, **fields})
            return "criada", written

        is_reference = row.get("Origem do vídeo") == ORIGEM_REFERENCIA
        for name, value in fields.items():
            current = row.get(name)
            if name in ("Origem do vídeo", "Status") and is_reference:
                write = False  # marcação manual da equipe: vídeo de referência não vira "Editado"
            elif name == "Origem do vídeo":
                write = current != value
            elif name == "Status":
                write = (current or "") in STATUS_UPGRADABLE and current != value
            elif regenerate and name in REGENERABLE:
                write = current != value and not (value is None or value == "")
            else:
                write = _is_empty(current) and not _is_empty(value)
            if write and (enc := self._encode(name, value)):
                props[name] = enc
                written[name] = value

        if not props:
            return "sem mudanças", written
        if dry_run:
            return "seria atualizada", written
        self._request("PATCH", f"/pages/{row.page_id}", json={"properties": props})
        row.values.update(written)
        return "atualizada", written

"""Validation minimale de JSON Schema pour les entrées d'outils.

Les arguments proposés par un modèle sont des données non fiables : on les
valide toujours avant d'exécuter quoi que ce soit (types, champs requis,
énumérations, champs inattendus).
"""
from __future__ import annotations

from typing import Any

_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def _type_ok(value: Any, expected: str) -> bool:
    if expected in ("integer", "number") and isinstance(value, bool):
        return False  # en Python, True est un int : on le refuse ici
    return isinstance(value, _TYPES.get(expected, (object,)))


def validate(value: Any, schema: dict, path: str = "$") -> list[str]:
    """Retourne la liste des erreurs (vide si l'entrée est valide)."""
    errors: list[str] = []
    expected = schema.get("type")
    if expected:
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(value, t) for t in allowed):
            return [f"{path}: type attendu {'/'.join(allowed)}, reçu {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: valeur {value!r} hors de {schema['enum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}.{name}: champ requis manquant")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in props:
                    errors.append(f"{path}.{name}: champ inattendu")
        for name, sub in props.items():
            if name in value:
                errors += validate(value[name], sub, f"{path}.{name}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors += validate(item, schema["items"], f"{path}[{index}]")
    return errors


def obj(properties: dict, required: list[str] | None = None) -> dict:
    """Raccourci : schéma d'objet strict (compatible avec le mode « strict » de Claude)."""
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }

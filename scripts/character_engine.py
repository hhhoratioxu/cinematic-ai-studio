from __future__ import annotations

from pathlib import Path

from common import resolve_asset, write_json
from models import Character, Plan


def prepare_characters(plan: Plan, image_engine, directory: Path, base: Path):
    directory.mkdir(parents=True, exist_ok=True)
    characters = []
    for original in plan.characters:
        character = original.model_copy(deep=True)
        for view, value in character.references.items():
            character.references[view] = str(resolve_asset(value, base))
        for view in ("front", "side", "full_body"):
            if view in character.references:
                continue
            refs = [Path(character.references["front"])] if "front" in character.references else []
            prompt = (f"Original character design for {plan.visual_style}. {character.identity()}. "
                      f"One {view.replace('_', ' ')} reference portrait, neutral studio background. "
                      "Preserve the exact face, hair, wardrobe and proportions of supplied references. "
                      "Single view only; no text or collage. Face clearly visible.")
            output = image_engine.generate(prompt, directory / f"{character.id}_{view}.png", refs)
            character.references[view] = str(output.resolve())
        characters.append(character)
        write_json(directory.parent / "characters.json", [c.model_dump() for c in characters])
    return characters


def merge_bible(plan: Plan, bible: list[Character]):
    """Explicit cross-episode reuse; reject silent identity/voice changes."""
    previous = {c.id: c for c in bible}
    result = []
    for current in plan.characters:
        old = previous.get(current.id)
        if old:
            for key in ("face", "hair", "build", "wardrobe", "voice", "style"):
                if getattr(old, key) != getattr(current, key):
                    raise ValueError(f"Character {current.id} changed {key}; explicitly version the Character ID")
            current = current.model_copy(update={"references": old.references})
        result.append(current)
    return plan.model_copy(update={"characters": result})

from __future__ import annotations

from pathlib import Path

from common import CinemaError, content_key, digest
from models import Settings
from providers.base import SyncJobs
from providers.openai_api import OpenAI


def rate(settings: Settings, name: str, units=1):
    if name not in settings.ceilings_usd:
        raise CinemaError(f"Set a reviewed USD cost ceiling for '{name}' in your config before generation")
    return settings.ceilings_usd[name] * units


class ImageEngine:
    def __init__(self, settings: Settings, ledger, provider=None):
        self.settings = settings
        self.jobs = SyncJobs(ledger)
        self.provider = provider

    def generate(self, prompt: str, output: Path, references=()):
        spec = {"prompt": prompt, "model": self.settings.image_model, "size": self.settings.image_size,
                "quality": self.settings.image_quality, "references": [digest(p) for p in references]}
        provider = self.provider or OpenAI()
        return self.jobs.run("openai", "image", spec, output, rate(self.settings, "openai:image"),
                             lambda p: provider.image(prompt, p, self.settings.image_model,
                                                      self.settings.image_size, self.settings.image_quality,
                                                      references))

    def scene(self, plan, shot, characters, directory: Path):
        prompt = (f"A single film first frame, {plan.visual_style}. {shot.camera} composition in "
                  f"{shot.environment}. {shot.lighting}. {shot.subject}. Starting pose before: {shot.action}. "
                  "Use all supplied character references with the same identities, hair, wardrobe and proportions. "
                  "No panels, collage, subtitles, logos or extra characters. " +
                  " ".join(c.identity() for c in characters))
        refs = [Path(c.references["front"]) for c in characters]
        output = directory / f"{shot.id}_{content_key(prompt)[:12]}.png"
        return self.generate(prompt, output, refs)

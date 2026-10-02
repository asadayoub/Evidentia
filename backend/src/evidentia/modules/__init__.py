"""Evidentia bounded-context packages.

Context packages do not re-export their public surfaces. Entrypoints and other
contexts must import ``evidentia.modules.<context>.public`` explicitly.

@skyhook-implements NFR-008
@skyhook-story STORY-008
"""

__all__: tuple[str, ...] = ()

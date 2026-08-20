# Witcher 3 starter knowledge corpus

Small demonstration corpus for GameSage's first local retrieval prototype.

## Format

Each `.md` file is one knowledge chunk:

- an HTML comment block starting with `gamesage-knowledge` holding
  `key: value` metadata (`id`, `title`, `source`, `url`, `license`,
  `section`, `spoiler`);
- followed by the chunk text in Markdown.

Files without the marker (like this README) are ignored by the loader.

## Content and licensing

Entries are short original summaries written for GameSage describing
widely known game facts — they are not excerpts from wikis. Each entry
may reference a canonical wiki page under `url`; those pages have their
own licenses (typically CC BY-SA on Fandom), which the entry records in
`license`.

Do not commit verbatim wiki text or third-party images here.

import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type CommunityGame = {
  id: string;
  display_name: string;
  origin: string;
  definition_id?: string;
  version?: string;
  author?: string;
};

type GameDefinitionEntry = {
  definition_id: string;
  status: string;
  message: string;
  game_id?: string | null;
  display_name?: string | null;
  version?: string | null;
  author?: string | null;
};

type KnowledgePackEntry = {
  pack_id: string;
  status: string;
  message: string;
  game_id?: string | null;
  name?: string | null;
  version?: string | null;
  author?: string | null;
  languages?: string[] | null;
  record_count?: number | null;
};

type CommunityContentData = {
  games: CommunityGame[];
  game_definitions: GameDefinitionEntry[];
  knowledge_packs: KnowledgePackEntry[];
};

type ContentState =
  | { status: "loading" }
  | { status: "ready"; data: CommunityContentData }
  | { status: "error"; message: string };

const STATUS_LABELS: Record<string, string> = {
  loaded: "Loaded",
  invalid: "Invalid",
  incompatible: "Incompatible",
  conflict: "Conflict",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`status-badge status-${status}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function Diagnostic({ message }: { message: string }) {
  if (!message) {
    return null;
  }
  return <p className="diagnostic">{message}</p>;
}

async function requestContent(): Promise<ContentState> {
  try {
    const data = await invoke<CommunityContentData>("community_content");
    return { status: "ready", data };
  } catch (error) {
    console.error("community_content failed:", error);
    if (typeof error === "object" && error !== null && "message" in error) {
      const candidate = error as { message?: unknown };
      if (typeof candidate.message === "string") {
        return { status: "error", message: candidate.message };
      }
    }
    return {
      status: "error",
      message: "The GameSage Python core could not be reached.",
    };
  }
}

function CommunityContent({ onClosed }: { onClosed: () => void }) {
  const [state, setState] = useState<ContentState>({ status: "loading" });

  useEffect(() => {
    void requestContent().then(setState);
  }, []);

  async function refresh() {
    setState({ status: "loading" });
    setState(await requestContent());
  }

  return (
    <section className="community-content">
      <div className="community-header">
        <h2>Community Content</h2>
        <button onClick={() => void refresh()} disabled={state.status === "loading"}>
          {state.status === "loading" ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {state.status === "error" && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}

      {state.status === "loading" && <p className="muted">Loading community content…</p>}

      {state.status === "ready" && (
        <>
          <h3>Games</h3>
          <ul className="content-list">
            {state.data.games.map((game) => (
              <li key={game.id} className="content-entry">
                <div className="entry-main">
                  <span className="entry-title">{game.display_name}</span>
                  <span className={`origin-badge origin-${game.origin}`}>
                    {game.origin === "native" ? "Native" : "Community"}
                  </span>
                </div>
                {game.origin === "community" && (
                  <div className="entry-meta">
                    <span>{game.definition_id}</span>
                    {game.version && <span> · {game.version}</span>}
                    {game.author && <span> · by {game.author}</span>}
                  </div>
                )}
              </li>
            ))}
          </ul>

          <h3>Game Definitions</h3>
          {state.data.game_definitions.length === 0 ? (
            <p className="muted">
              No community Game Definitions are installed. Built-in games work without
              them.
            </p>
          ) : (
            <ul className="content-list">
              {state.data.game_definitions.map((definition) => (
                <li
                  key={`${definition.definition_id}:${definition.message}`}
                  className="content-entry"
                >
                  <div className="entry-main">
                    <span className="entry-title">
                      {definition.display_name ?? definition.definition_id}
                    </span>
                    <StatusBadge status={definition.status} />
                  </div>
                  <div className="entry-meta">
                    <span>{definition.definition_id}</span>
                    {definition.game_id && <span> · game: {definition.game_id}</span>}
                    {definition.version && <span> · {definition.version}</span>}
                    {definition.author && <span> · by {definition.author}</span>}
                  </div>
                  <Diagnostic message={definition.message} />
                </li>
              ))}
            </ul>
          )}

          <h3>Knowledge Packs</h3>
          <KnowledgePackList
            packs={state.data.knowledge_packs}
            games={state.data.games}
          />
        </>
      )}

      <button className="back-button" onClick={onClosed}>
        ← Back to Assistant
      </button>
    </section>
  );
}

function KnowledgePackList({
  packs,
  games,
}: {
  packs: KnowledgePackEntry[];
  games: CommunityGame[];
}) {
  if (packs.length === 0) {
    return <p className="muted">No Knowledge Packs are installed.</p>;
  }

  const displayNames = new Map(games.map((game) => [game.id, game.display_name]));
  const groups = new Map<string, KnowledgePackEntry[]>();
  for (const pack of packs) {
    const key = pack.game_id ?? "";
    const entries = groups.get(key) ?? [];
    entries.push(pack);
    groups.set(key, entries);
  }

  return (
    <>
      {[...groups.entries()].map(([gameId, entries]) => (
        <div key={gameId || "unknown"} className="pack-group">
          <h4>
            {displayNames.get(gameId) ?? "Unknown / unavailable game"}
            {!displayNames.has(gameId) && gameId && (
              <span className="muted"> (game_id: {gameId})</span>
            )}
          </h4>
          <ul className="content-list">
            {entries.map((pack) => (
              <li key={pack.pack_id} className="content-entry">
                <div className="entry-main">
                  <span className="entry-title">{pack.name ?? pack.pack_id}</span>
                  <StatusBadge status={pack.status} />
                </div>
                <div className="entry-meta">
                  <span>{pack.pack_id}</span>
                  {pack.version && <span> · {pack.version}</span>}
                  {pack.author && <span> · by {pack.author}</span>}
                  {pack.record_count != null && <span> · {pack.record_count} records</span>}
                  {pack.languages && pack.languages.length > 0 && (
                    <span> · {pack.languages.join(", ")}</span>
                  )}
                </div>
                <Diagnostic message={pack.status !== "loaded" ? pack.message : ""} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}

export default CommunityContent;

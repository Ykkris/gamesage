import { useEffect, useRef, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { openUrl } from "@tauri-apps/plugin-opener";
import "./App.css";

type GameInfo = {
  id: string;
  display_name: string;
};

type GamesState =
  | { status: "loading" }
  | { status: "ready"; games: GameInfo[]; selectedId: string }
  | { status: "error"; message: string };

type CaptureSuccess = {
  kind: "success";
  game_id: string;
  window_title: string;
  width: number;
  height: number;
  screenshot_path: string;
};

type GameError = {
  kind: "game_error";
  code: string;
  message: string;
};

type CaptureState =
  | { status: "idle" }
  | { status: "capturing" }
  | { status: "success"; result: CaptureSuccess }
  | { status: "error"; code: string | undefined; message: string };

type KnowledgeSource = {
  title: string;
  source: string;
  url: string;
};

type AskSuccess = {
  kind: "success";
  answer: string;
  provider: string;
  model: string;
  sources?: KnowledgeSource[];
};

type AskState =
  | { status: "idle" }
  | { status: "asking" }
  | {
      status: "answered";
      answer: string;
      provider: string;
      model: string;
      sources: KnowledgeSource[];
    }
  | { status: "error"; message: string };

/** Emitted by the Rust layer when the global Ctrl+F8 shortcut is pressed. */
const CAPTURE_REQUESTED_EVENT = "capture-requested";

function bridgeErrorDetails(error: unknown): {
  code: string | undefined;
  message: string;
} {
  if (typeof error === "object" && error !== null && "message" in error) {
    const candidate = error as { message?: unknown; code?: unknown };
    if (typeof candidate.message === "string") {
      return {
        code: typeof candidate.code === "string" ? candidate.code : undefined,
        message: candidate.message,
      };
    }
  }
  return { code: undefined, message: "The GameSage Python core could not be reached." };
}

async function requestGames(): Promise<GamesState> {
  try {
    const response = await invoke<{ games: GameInfo[]; default_game: string }>(
      "supported_games"
    );
    if (response.games.length === 0) {
      return { status: "error", message: "No supported games are available." };
    }
    const selectedId = response.games.some((game) => game.id === response.default_game)
      ? response.default_game
      : response.games[0].id;
    return { status: "ready", games: response.games, selectedId };
  } catch (error) {
    console.error("supported_games failed:", error);
    return { status: "error", message: bridgeErrorDetails(error).message };
  }
}

async function requestCapture(gameId: string): Promise<CaptureState> {
  try {
    const response = await invoke<CaptureSuccess | GameError>("capture_game", { gameId });
    if (response.kind === "success") {
      return { status: "success", result: response };
    }
    return { status: "error", code: response.code, message: response.message };
  } catch (error) {
    console.error("capture_game failed:", error);
    const details = bridgeErrorDetails(error);
    return { status: "error", code: details.code, message: details.message };
  }
}

async function requestAnalysis(
  image: string,
  question: string,
  gameId: string
): Promise<AskState> {
  try {
    const response = await invoke<AskSuccess | GameError>("analyze_game", {
      image,
      question,
      gameId,
    });
    if (response.kind === "success") {
      return {
        status: "answered",
        answer: response.answer,
        provider: response.provider,
        model: response.model,
        sources: response.sources ?? [],
      };
    }
    return { status: "error", message: response.message };
  } catch (error) {
    console.error("analyze_game failed:", error);
    return { status: "error", message: bridgeErrorDetails(error).message };
  }
}

function App() {
  const [games, setGames] = useState<GamesState>({ status: "loading" });
  const selectedGameId = games.status === "ready" ? games.selectedId : null;
  // Mirrored for the global-shortcut handler, which must not go stale.
  const selectedGameIdRef = useRef<string | null>(null);
  useEffect(() => {
    selectedGameIdRef.current = selectedGameId;
  }, [selectedGameId]);

  const [state, setState] = useState<CaptureState>({ status: "idle" });
  const captureInFlight = useRef(false);

  const [question, setQuestion] = useState("");
  const [askState, setAskState] = useState<AskState>({ status: "idle" });
  const askInFlight = useRef(false);

  // A capture belongs to the game that produced it; Ask always uses that id.
  const capture = state.status === "success" ? state.result : undefined;
  const currentImage = capture?.screenshot_path;
  const capturedGameId = capture?.game_id;
  const canAsk =
    currentImage !== undefined && question.trim() !== "" && askState.status !== "asking";

  // Single capture flow for the button and the global shortcut; while a
  // capture runs, further triggers are coalesced away.
  async function handleCapture() {
    if (captureInFlight.current) {
      return;
    }
    const gameId = selectedGameIdRef.current;
    if (!gameId) {
      setState({
        status: "error",
        code: undefined,
        message: "No game is selected.",
      });
      return;
    }
    captureInFlight.current = true;
    setState({ status: "capturing" });
    try {
      setState(await requestCapture(gameId));
    } finally {
      captureInFlight.current = false;
    }
  }

  async function handleAsk() {
    if (!canAsk || askInFlight.current || !currentImage || !capturedGameId) {
      return;
    }
    askInFlight.current = true;
    setAskState({ status: "asking" });
    try {
      setAskState(await requestAnalysis(currentImage, question.trim(), capturedGameId));
    } finally {
      askInFlight.current = false;
    }
  }

  useEffect(() => {
    const subscription = listen(CAPTURE_REQUESTED_EVENT, () => {
      void handleCapture();
    });
    return () => {
      void subscription.then((unlisten) => unlisten());
    };
    // handleCapture only touches stable state (setState, ref) — mount once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void requestGames().then(setGames);
  }, []);

  // A new capture invalidates the previous question and answer.
  useEffect(() => {
    setQuestion("");
    setAskState({ status: "idle" });
  }, [currentImage, capturedGameId]);

  function selectGame(id: string) {
    if (games.status === "ready") {
      setGames({ ...games, selectedId: id });
    }
  }

  return (
    <main className="container">
      <header className="header">
        <h1>GameSage</h1>
        {games.status === "loading" && (
          <p className="subtitle">Loading supported games…</p>
        )}
        {games.status === "error" && (
          <p className="error" role="alert">
            {games.message}
          </p>
        )}
        {games.status === "ready" &&
          (games.games.length > 1 ? (
            <select
              className="game-select"
              value={games.selectedId}
              onChange={(event) => selectGame(event.currentTarget.value)}
              aria-label="Selected game"
            >
              {games.games.map((game) => (
                <option key={game.id} value={game.id}>
                  {game.display_name}
                </option>
              ))}
            </select>
          ) : (
            <p className="subtitle">Current game: {games.games[0].display_name}</p>
          ))}
      </header>

      <button
        className="capture-button"
        onClick={() => void handleCapture()}
        disabled={state.status === "capturing" || selectedGameId === null}
      >
        {state.status === "capturing" ? "Capturing…" : "Capture Game"}
      </button>
      <p className="shortcut-hint">or press Ctrl+F8 while playing</p>

      {state.status === "success" && (
        <section className="capture-result">
          <img
            className="screenshot"
            src={convertFileSrc(state.result.screenshot_path)}
            alt={`Capture (${state.result.width}x${state.result.height})`}
          />
          <dl className="capture-details">
            <div>
              <dt>Window</dt>
              <dd>{state.result.window_title}</dd>
            </div>
            <div>
              <dt>Resolution</dt>
              <dd>
                {state.result.width} × {state.result.height}
              </dd>
            </div>
          </dl>
        </section>
      )}

      {state.status === "error" && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}

      <section className="ask-section">
        <form
          className="ask-form"
          onSubmit={(event) => {
            event.preventDefault();
            void handleAsk();
          }}
        >
          <input
            className="question-input"
            value={question}
            onChange={(event) => setQuestion(event.currentTarget.value)}
            placeholder="Ask about this screenshot…"
            disabled={currentImage === undefined}
            aria-label="Question about the screenshot"
          />
          <button type="submit" disabled={!canAsk}>
            {askState.status === "asking" ? "Asking…" : "Ask GameSage"}
          </button>
        </form>

        {askState.status === "answered" && (
          <div className="answer">
            <p className="answer-text">{askState.answer}</p>
            <p className="answer-meta">
              answered by {askState.provider} · {askState.model}
            </p>
            {askState.sources.length > 0 && (
              <div className="sources">
                <p className="sources-heading">Sources</p>
                <ul>
                  {askState.sources.map((item) => (
                    <li key={`${item.title}:${item.url}`}>
                      <span>
                        {item.title} — {item.source}
                      </span>
                      {item.url && (
                        <button
                          className="source-link"
                          onClick={() => void openUrl(item.url).catch(console.error)}
                        >
                          reference
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {askState.status === "error" && (
          <p className="error" role="alert">
            {askState.message}
          </p>
        )}
      </section>
    </main>
  );
}

export default App;

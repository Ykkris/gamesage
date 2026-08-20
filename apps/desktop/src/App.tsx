import { useEffect, useRef, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import "./App.css";

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

async function requestCapture(): Promise<CaptureState> {
  try {
    const response = await invoke<CaptureSuccess | GameError>("capture_game");
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

function App() {
  const [state, setState] = useState<CaptureState>({ status: "idle" });
  const captureInFlight = useRef(false);

  // Single capture flow for both the button and the global shortcut:
  // while a capture runs, further triggers are coalesced away.
  async function handleCapture() {
    if (captureInFlight.current) {
      return;
    }
    captureInFlight.current = true;
    setState({ status: "capturing" });
    try {
      setState(await requestCapture());
    } finally {
      captureInFlight.current = false;
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

  return (
    <main className="container">
      <header className="header">
        <h1>GameSage</h1>
        <p className="subtitle">Current game: The Witcher 3: Wild Hunt</p>
      </header>

      <button
        className="capture-button"
        onClick={() => void handleCapture()}
        disabled={state.status === "capturing"}
      >
        {state.status === "capturing" ? "Capturing…" : "Capture Game"}
      </button>
      <p className="shortcut-hint">or press Ctrl+F8 while playing</p>

      {state.status === "success" && (
        <section className="capture-result">
          <img
            className="screenshot"
            src={convertFileSrc(state.result.screenshot_path)}
            alt={`Witcher 3 capture (${state.result.width}x${state.result.height})`}
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
    </main>
  );
}

export default App;

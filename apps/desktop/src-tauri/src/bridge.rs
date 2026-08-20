//! Thin bridge to the Python GameSage core.
//!
//! One-shot invocation strategy: spawn the repository's Python interpreter
//! (``.venv/Scripts/python.exe``) with ``-m companion.api capture``, read the
//! single-line JSON envelope from stdout, and hand a typed result to the
//! frontend. No detection/capture logic lives here.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::PathBuf;
use std::process::Command;

/// Repository root: this crate lives at `<repo>/apps/desktop/src-tauri`,
/// so the root is three parent levels above the manifest directory.
///
/// Derived from the compile-time checkout location; valid for the
/// development prototype only. Canonicalized for clean absolute paths,
/// with the joined path as fallback if resolution fails.
pub fn repo_root() -> PathBuf {
    let joined = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..");
    joined.canonicalize().unwrap_or(joined)
}

/// The Python executable used to run the GameSage core.
///
/// Strategy is isolated here so it can change later (bundled interpreter,
/// configured path, ...). The `GAMESAGE_PYTHON` environment variable
/// overrides the repository virtualenv.
pub fn python_executable() -> PathBuf {
    if let Ok(custom) = std::env::var("GAMESAGE_PYTHON") {
        return PathBuf::from(custom);
    }
    repo_root()
        .join(".venv")
        .join("Scripts")
        .join("python.exe")
}

/// Working directory for the backend CLI: the repository root, where the
/// `companion` package is importable and `screenshots/` is written.
pub fn backend_working_dir() -> PathBuf {
    repo_root()
}

/// Result of one capture request, ready for the frontend.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum CaptureResponse {
    Success {
        game_id: String,
        window_title: String,
        width: u32,
        height: u32,
        screenshot_path: String,
    },
    GameError {
        code: String,
        message: String,
    },
}

/// Bridge-level failure (Python core could not run or misbehaved).
#[derive(Debug, Clone, Serialize)]
pub struct BridgeError {
    pub code: &'static str,
    pub message: String,
}

impl BridgeError {
    fn new(code: &'static str, message: String) -> Self {
        Self { code, message }
    }
}

#[derive(Debug, Deserialize)]
struct SuccessPayload {
    game_id: String,
    window_title: String,
    width: u32,
    height: u32,
    screenshot_path: String,
}

#[derive(Debug, Deserialize)]
struct ErrorPayload {
    code: String,
    message: String,
}

/// Parse the JSON envelope printed by `python -m companion.api capture`.
pub fn parse_envelope(stdout: &str) -> Result<CaptureResponse, BridgeError> {
    let value: Value = serde_json::from_str(stdout.trim()).map_err(|error| {
        BridgeError::new(
            "invalid_backend_response",
            format!("The GameSage core returned invalid JSON: {error}."),
        )
    })?;
    match value.get("ok").and_then(Value::as_bool) {
        Some(true) => {
            let payload: SuccessPayload = serde_json::from_value(value).map_err(|error| {
                BridgeError::new(
                    "invalid_backend_response",
                    format!("The GameSage core returned an unexpected response: {error}."),
                )
            })?;
            Ok(CaptureResponse::Success {
                game_id: payload.game_id,
                window_title: payload.window_title,
                width: payload.width,
                height: payload.height,
                screenshot_path: payload.screenshot_path,
            })
        }
        Some(false) => {
            let error_value = value.get("error").cloned().unwrap_or(Value::Null);
            let payload: ErrorPayload = serde_json::from_value(error_value).map_err(|error| {
                BridgeError::new(
                    "invalid_backend_response",
                    format!("The GameSage core error response was malformed: {error}."),
                )
            })?;
            Ok(CaptureResponse::GameError {
                code: payload.code,
                message: payload.message,
            })
        }
        None => Err(BridgeError::new(
            "invalid_backend_response",
            "The GameSage core response is missing the 'ok' field.".to_string(),
        )),
    }
}

/// Spawn the Python core CLI and return its stdout.
fn run_python_capture() -> Result<String, BridgeError> {
    let python = python_executable();
    let mut command = Command::new(&python);
    command
        .args(["-m", "companion.api", "capture"])
        .current_dir(backend_working_dir());
    // Avoid flashing a console window alongside the GUI app.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let output = command.output().map_err(|error| {
        BridgeError::new(
            "python_invocation_failed",
            format!(
                "Could not start the GameSage Python core at {}: {error}.",
                python.display()
            ),
        )
    })?;

    let stdout = String::from_utf8_lossy(&output.stdout).into_owned();
    let stderr = String::from_utf8_lossy(&output.stderr).trim_end().to_string();
    if !stderr.is_empty() {
        // Diagnostic details for the development console only; never shown
        // as the user-facing error (e.g. ModuleNotFoundError output).
        eprintln!("gamesage core stderr: {stderr}");
    }
    if stdout.trim().is_empty() {
        eprintln!(
            "gamesage core produced no response (status {:?}, working dir {})",
            output.status.code(),
            backend_working_dir().display()
        );
        return Err(BridgeError::new(
            "invalid_backend_response",
            format!(
                "The GameSage core exited with status {:?} without producing a response.",
                output.status.code()
            ),
        ));
    }
    Ok(stdout)
}

fn capture_via_python() -> Result<CaptureResponse, BridgeError> {
    let stdout = run_python_capture()?;
    parse_envelope(&stdout)
}

#[tauri::command]
pub async fn capture_game() -> Result<CaptureResponse, BridgeError> {
    tauri::async_runtime::spawn_blocking(capture_via_python)
        .await
        .map_err(|error| {
            BridgeError::new(
                "backend_task_failed",
                format!("The capture task could not be completed: {error}."),
            )
        })?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_success_envelope() {
        let stdout = r#"{"ok": true, "game_id": "witcher3", "window_title": "The Witcher 3", "width": 2560, "height": 1440, "screenshot_path": "C:\\x\\shots\\a.png"}"#;
        match parse_envelope(stdout) {
            Ok(CaptureResponse::Success {
                game_id,
                window_title,
                width,
                height,
                screenshot_path,
            }) => {
                assert_eq!(game_id, "witcher3");
                assert_eq!(window_title, "The Witcher 3");
                assert_eq!((width, height), (2560, 1440));
                assert_eq!(screenshot_path, r"C:\x\shots\a.png");
            }
            other => panic!("expected success, got {other:?}"),
        }
    }

    #[test]
    fn parses_game_error_envelope() {
        let stdout = r#"{"ok": false, "error": {"code": "game_not_running", "message": "The Witcher 3: Wild Hunt does not appear to be running."}}"#;
        match parse_envelope(stdout) {
            Ok(CaptureResponse::GameError { code, message }) => {
                assert_eq!(code, "game_not_running");
                assert!(message.contains("running"));
            }
            other => panic!("expected game error, got {other:?}"),
        }
    }

    #[test]
    fn rejects_invalid_json() {
        let error = parse_envelope("not json at all").unwrap_err();
        assert_eq!(error.code, "invalid_backend_response");
    }

    #[test]
    fn rejects_missing_ok_field() {
        let error = parse_envelope(r#"{"game_id": "witcher3"}"#).unwrap_err();
        assert_eq!(error.code, "invalid_backend_response");
    }

    #[test]
    fn rejects_success_with_missing_fields() {
        let error = parse_envelope(r#"{"ok": true, "game_id": "witcher3"}"#).unwrap_err();
        assert_eq!(error.code, "invalid_backend_response");
    }

    #[test]
    fn repo_root_resolves_above_apps() {
        let root = repo_root();
        // The manifest directory must be exactly <root>/apps/desktop/src-tauri.
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .canonicalize()
            .expect("manifest dir should canonicalize");
        assert_eq!(root.join("apps").join("desktop").join("src-tauri"), manifest);
        assert!(root.ends_with("GameSage"));
        assert!(!root.ends_with("apps"));
        assert!(!root.ends_with("desktop"));
        assert!(!root.ends_with("src-tauri"));
    }

    #[test]
    fn backend_working_dir_is_repo_root_and_contains_companion_package() {
        let working_dir = backend_working_dir();
        assert_eq!(working_dir, repo_root());
        // The `companion` package must be importable from this directory.
        assert!(working_dir.join("companion").join("api").is_dir());
    }

    #[test]
    fn python_executable_resolves_default_then_override() {
        // SAFETY: single test touches this variable, no parallel races.
        std::env::remove_var("GAMESAGE_PYTHON");
        assert_eq!(
            python_executable(),
            repo_root()
                .join(".venv")
                .join("Scripts")
                .join("python.exe")
        );
        assert!(python_executable().ends_with(".venv\\Scripts\\python.exe"));

        std::env::set_var("GAMESAGE_PYTHON", r"C:\custom\python.exe");
        assert_eq!(python_executable(), PathBuf::from(r"C:\custom\python.exe"));
        std::env::remove_var("GAMESAGE_PYTHON");
    }
}

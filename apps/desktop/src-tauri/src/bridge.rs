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

/// Run a subprocess with fully explicit stdio:
///
/// - stdout and stderr always piped (captured for the JSON envelope);
/// - stdin piped only when a payload must be written, else null;
/// - the stdin pipe is closed after writing so the child sees EOF.
fn execute_with_optional_stdin(
    mut command: Command,
    stdin_data: Option<String>,
) -> Result<std::process::Output, String> {
    command.stdin(if stdin_data.is_some() {
        std::process::Stdio::piped()
    } else {
        std::process::Stdio::null()
    });
    command.stdout(std::process::Stdio::piped());
    command.stderr(std::process::Stdio::piped());

    let mut child = command
        .spawn()
        .map_err(|error| format!("could not start the process: {error}"))?;
    if let Some(data) = stdin_data {
        use std::io::Write;
        let stdin = child
            .stdin
            .as_mut()
            .expect("stdin is piped when a payload exists");
        stdin
            .write_all(data.as_bytes())
            .map_err(|error| format!("could not write the stdin payload: {error}"))?;
    }
    // Dropping stdin closes the pipe so Python sees EOF after the payload.
    drop(child.stdin.take());

    child
        .wait_with_output()
        .map_err(|error| format!("could not collect the process output: {error}"))
}

/// Extract the captured stdout, logging stderr and failing clearly when
/// the core produced no machine-readable response.
fn stdout_or_backend_error(output: std::process::Output) -> Result<String, BridgeError> {
    let stdout = String::from_utf8_lossy(&output.stdout).into_owned();
    let stderr = String::from_utf8_lossy(&output.stderr).trim_end().to_string();
    if !stderr.is_empty() {
        // Diagnostic details for the development console only; never shown
        // as the user-facing error (e.g. provider or module errors).
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

/// Spawn the Python core CLI with ``args`` and return its stdout.
///
/// ``stdin_data`` optionally writes one structured payload (session
/// context JSON) to the subprocess; Rust transports it verbatim and never
/// interprets or formats the conversation.
fn run_python_with_stdin(
    args: &[String],
    stdin_data: Option<String>,
) -> Result<String, BridgeError> {
    let python = python_executable();
    let mut command = Command::new(&python);
    command.args(args).current_dir(backend_working_dir());
    // Avoid flashing a console window alongside the GUI app.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let output = execute_with_optional_stdin(command, stdin_data).map_err(|error| {
        BridgeError::new(
            "python_invocation_failed",
            format!(
                "Could not run the GameSage Python core at {}: {error}.",
                python.display()
            ),
        )
    })?;
    stdout_or_backend_error(output)
}

fn run_python(args: &[String]) -> Result<String, BridgeError> {
    run_python_with_stdin(args, None)
}

fn push_game_arg(args: &mut Vec<String>, game_id: Option<&str>) {
    if let Some(id) = game_id {
        args.push("--game".into());
        args.push(id.to_string());
    }
}

fn capture_args(game_id: Option<&str>) -> Vec<String> {
    let mut args: Vec<String> = ["-m", "companion.api", "capture"]
        .iter()
        .map(|arg| arg.to_string())
        .collect();
    push_game_arg(&mut args, game_id);
    args
}

fn analyze_args(
    image: &str,
    question: &str,
    game_id: Option<&str>,
    with_session_context: bool,
) -> Vec<String> {
    let mut args = vec![
        "-m".into(),
        "companion.api".into(),
        "analyze".into(),
        "--image".into(),
        image.into(),
        "--question".into(),
        question.into(),
    ];
    push_game_arg(&mut args, game_id);
    if with_session_context {
        // The context itself travels as JSON over stdin, not argv.
        args.push("--context".into());
        args.push("-".into());
    }
    args
}

fn capture_via_python(game_id: Option<String>) -> Result<CaptureResponse, BridgeError> {
    let stdout = run_python(&capture_args(game_id.as_deref()))?;
    parse_envelope(&stdout)
}

#[tauri::command]
pub async fn capture_game(game_id: Option<String>) -> Result<CaptureResponse, BridgeError> {
    tauri::async_runtime::spawn_blocking(move || capture_via_python(game_id))
        .await
        .map_err(|error| {
            BridgeError::new(
                "backend_task_failed",
                format!("The capture task could not be completed: {error}."),
            )
        })?
}

/// Result of one analysis request, ready for the frontend.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum AnalyzeResponse {
    Success {
        answer: String,
        provider: String,
        model: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        sources: Option<Vec<SourceInfo>>,
    },
    GameError {
        code: String,
        message: String,
    },
}

/// One knowledge source used by an answer.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceInfo {
    pub title: String,
    pub source: String,
    pub url: String,
}

#[derive(Debug, Deserialize)]
struct AnalyzeSuccessPayload {
    answer: String,
    provider: String,
    model: String,
    #[serde(default)]
    sources: Option<Vec<SourceInfo>>,
}

/// Parse the JSON envelope printed by `python -m companion.api analyze`.
pub fn parse_analyze_envelope(stdout: &str) -> Result<AnalyzeResponse, BridgeError> {
    let value: Value = serde_json::from_str(stdout.trim()).map_err(|error| {
        BridgeError::new(
            "invalid_backend_response",
            format!("The GameSage core returned invalid JSON: {error}."),
        )
    })?;
    match value.get("ok").and_then(Value::as_bool) {
        Some(true) => {
            let payload: AnalyzeSuccessPayload = serde_json::from_value(value).map_err(|error| {
                BridgeError::new(
                    "invalid_backend_response",
                    format!("The GameSage core returned an unexpected response: {error}."),
                )
            })?;
            Ok(AnalyzeResponse::Success {
                answer: payload.answer,
                provider: payload.provider,
                model: payload.model,
                sources: payload.sources,
            })
        }
        Some(false) => parse_game_error(&value),
        None => Err(BridgeError::new(
            "invalid_backend_response",
            "The GameSage core response is missing the 'ok' field.".to_string(),
        )),
    }
}

fn parse_game_error(value: &Value) -> Result<AnalyzeResponse, BridgeError> {
    let error_value = value.get("error").cloned().unwrap_or(Value::Null);
    let error = match serde_json::from_value::<ErrorPayload>(error_value) {
        Ok(payload) => payload,
        Err(error) => {
            return Err(BridgeError::new(
                "invalid_backend_response",
                format!("The GameSage core error response was malformed: {error}."),
            ))
        }
    };
    Ok(AnalyzeResponse::GameError {
        code: error.code,
        message: error.message,
    })
}

/// One recent conversational turn, transported verbatim to the Python core.
/// Rust never filters or formats these.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SessionTurn {
    pub game_id: String,
    pub question: String,
    pub answer: String,
}

fn analyze_via_python(
    image: String,
    question: String,
    game_id: Option<String>,
    session_context: Option<Vec<SessionTurn>>,
) -> Result<AnalyzeResponse, BridgeError> {
    let context_json = session_context
        .map(|turns| {
            serde_json::to_string(&turns).map_err(|error| {
                BridgeError::new(
                    "invalid_backend_response",
                    format!("Could not serialize session context: {error}."),
                )
            })
        })
        .transpose()?;
    let stdout = run_python_with_stdin(
        &analyze_args(&image, &question, game_id.as_deref(), context_json.is_some()),
        context_json,
    )?;
    parse_analyze_envelope(&stdout)
}

#[tauri::command]
pub async fn analyze_game(
    image: String,
    question: String,
    game_id: Option<String>,
    session_context: Option<Vec<SessionTurn>>,
) -> Result<AnalyzeResponse, BridgeError> {
    tauri::async_runtime::spawn_blocking(move || {
        analyze_via_python(image, question, game_id, session_context)
    })
    .await
    .map_err(|error| {
        BridgeError::new(
            "backend_task_failed",
            format!("The analysis task could not be completed: {error}."),
        )
    })?
}

/// Metadata for one registered game.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GameInfo {
    pub id: String,
    pub display_name: String,
    #[serde(default)]
    pub origin: Option<String>,
}

/// Supported games from the Python registry (the Rust layer holds no game list).
#[derive(Debug, Clone, Serialize)]
pub struct GamesResponse {
    pub games: Vec<GameInfo>,
    pub default_game: String,
}

#[derive(Debug, Deserialize)]
struct GamesPayload {
    games: Vec<GameInfo>,
    default_game: String,
}

/// Parse the JSON envelope printed by `python -m companion.api games`.
pub fn parse_games_envelope(stdout: &str) -> Result<GamesResponse, BridgeError> {
    let value: Value = serde_json::from_str(stdout.trim()).map_err(|error| {
        BridgeError::new(
            "invalid_backend_response",
            format!("The GameSage core returned invalid JSON: {error}."),
        )
    })?;
    if value.get("ok").and_then(Value::as_bool) != Some(true) {
        return Err(BridgeError::new(
            "invalid_backend_response",
            "The GameSage core games response was malformed.".to_string(),
        ));
    }
    let payload: GamesPayload = serde_json::from_value(value).map_err(|error| {
        BridgeError::new(
            "invalid_backend_response",
            format!("The GameSage core games response was malformed: {error}."),
        )
    })?;
    Ok(GamesResponse {
        games: payload.games,
        default_game: payload.default_game,
    })
}

fn games_args() -> Vec<String> {
    ["-m", "companion.api", "games"]
        .iter()
        .map(|arg| arg.to_string())
        .collect()
}

fn games_via_python() -> Result<GamesResponse, BridgeError> {
    let stdout = run_python(&games_args())?;
    parse_games_envelope(&stdout)
}

#[tauri::command]
pub async fn supported_games() -> Result<GamesResponse, BridgeError> {
    tauri::async_runtime::spawn_blocking(games_via_python)
        .await
        .map_err(|error| {
            BridgeError::new(
                "backend_task_failed",
                format!("The supported-games task could not be completed: {error}."),
            )
        })?
}

/// One supported game in the Community Content report.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CommunityGame {
    pub id: String,
    pub display_name: String,
    pub origin: String,
    #[serde(default)]
    pub definition_id: Option<String>,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub author: Option<String>,
}

/// One discovered Game Definition with its status.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GameDefinitionEntry {
    pub definition_id: String,
    pub status: String,
    pub message: String,
    #[serde(default)]
    pub game_id: Option<String>,
    #[serde(default)]
    pub display_name: Option<String>,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub author: Option<String>,
}

/// One discovered Knowledge Pack with its status.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct KnowledgePackEntry {
    pub pack_id: String,
    pub status: String,
    pub message: String,
    #[serde(default)]
    pub game_id: Option<String>,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub author: Option<String>,
    #[serde(default)]
    pub languages: Option<Vec<String>>,
    #[serde(default)]
    pub record_count: Option<u32>,
}

/// Read-only Community Content report (games, definitions, packs).
#[derive(Debug, Clone, Serialize)]
pub struct CommunityContent {
    pub games: Vec<CommunityGame>,
    pub game_definitions: Vec<GameDefinitionEntry>,
    pub knowledge_packs: Vec<KnowledgePackEntry>,
}

#[derive(Debug, Deserialize)]
struct CommunityPayload {
    games: Vec<CommunityGame>,
    game_definitions: Vec<GameDefinitionEntry>,
    knowledge_packs: Vec<KnowledgePackEntry>,
}

/// Parse the JSON envelope printed by `python -m companion.api community-content`.
pub fn parse_community_envelope(stdout: &str) -> Result<CommunityContent, BridgeError> {
    let value: Value = serde_json::from_str(stdout.trim()).map_err(|error| {
        BridgeError::new(
            "invalid_backend_response",
            format!("The GameSage core returned invalid JSON: {error}."),
        )
    })?;
    if value.get("ok").and_then(Value::as_bool) != Some(true) {
        return Err(BridgeError::new(
            "invalid_backend_response",
            "The GameSage core community-content response was malformed.".to_string(),
        ));
    }
    let payload: CommunityPayload = serde_json::from_value(value).map_err(|error| {
        BridgeError::new(
            "invalid_backend_response",
            format!("The GameSage core community-content response was malformed: {error}."),
        )
    })?;
    Ok(CommunityContent {
        games: payload.games,
        game_definitions: payload.game_definitions,
        knowledge_packs: payload.knowledge_packs,
    })
}

fn community_args() -> Vec<String> {
    ["-m", "companion.api", "community-content"]
        .iter()
        .map(|arg| arg.to_string())
        .collect()
}

fn community_via_python() -> Result<CommunityContent, BridgeError> {
    let stdout = run_python(&community_args())?;
    parse_community_envelope(&stdout)
}

#[tauri::command]
pub async fn community_content() -> Result<CommunityContent, BridgeError> {
    tauri::async_runtime::spawn_blocking(community_via_python)
        .await
        .map_err(|error| {
            BridgeError::new(
                "backend_task_failed",
                format!("The community-content task could not be completed: {error}."),
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

    #[test]
    fn parses_analyze_success_envelope() {
        let stdout = r#"{"ok": true, "answer": "You are near Oxenfurt.", "provider": "zai", "model": "glm-4.5v"}"#;
        match parse_analyze_envelope(stdout) {
            Ok(AnalyzeResponse::Success {
                answer,
                provider,
                model,
                sources,
            }) => {
                assert_eq!(answer, "You are near Oxenfurt.");
                assert_eq!(provider, "zai");
                assert_eq!(model, "glm-4.5v");
                assert!(sources.is_none(), "responses without knowledge stay backward compatible");
            }
            other => panic!("expected analyze success, got {other:?}"),
        }
    }

    #[test]
    fn parses_analyze_success_with_sources() {
        let stdout = r#"{"ok": true, "answer": "Use your Witcher Senses.", "provider": "openai_compatible", "model": "local", "sources": [{"title": "Witcher Senses (mechanic)", "source": "GameSage starter corpus", "url": "https://witcher.fandom.com/wiki/Witcher_Senses"}]}"#;
        match parse_analyze_envelope(stdout) {
            Ok(AnalyzeResponse::Success { sources, .. }) => {
                let sources = sources.expect("sources must be present");
                assert_eq!(sources.len(), 1);
                assert_eq!(sources[0].title, "Witcher Senses (mechanic)");
                assert_eq!(sources[0].source, "GameSage starter corpus");
                assert!(sources[0].url.starts_with("https://"));
            }
            other => panic!("expected analyze success, got {other:?}"),
        }
    }

    #[test]
    fn parses_analyze_game_error_envelope() {
        let stdout = r#"{"ok": false, "error": {"code": "provider_not_configured", "message": "Z.AI API key is not configured."}}"#;
        match parse_analyze_envelope(stdout) {
            Ok(AnalyzeResponse::GameError { code, message }) => {
                assert_eq!(code, "provider_not_configured");
                assert!(message.contains("API key"));
            }
            other => panic!("expected analyze game error, got {other:?}"),
        }
    }

    #[test]
    fn analyze_rejects_invalid_json_and_missing_fields() {
        assert_eq!(
            parse_analyze_envelope("not json").unwrap_err().code,
            "invalid_backend_response"
        );
        assert_eq!(
            parse_analyze_envelope(r#"{"answer": "x"}"#).unwrap_err().code,
            "invalid_backend_response"
        );
        assert_eq!(
            parse_analyze_envelope(r#"{"ok": true, "answer": "x"}"#)
                .unwrap_err()
                .code,
            "invalid_backend_response"
        );
    }

    #[test]
    fn analyze_args_pass_image_question_and_game_safely() {
        let args = analyze_args(
            r"D:\shots\witcher 3.png",
            "What quest is this? (spoiler-free)",
            Some("witcher3"),
            false,
        );
        assert_eq!(
            args,
            vec![
                "-m".to_string(),
                "companion.api".to_string(),
                "analyze".to_string(),
                "--image".to_string(),
                r"D:\shots\witcher 3.png".to_string(),
                "--question".to_string(),
                "What quest is this? (spoiler-free)".to_string(),
                "--game".to_string(),
                "witcher3".to_string(),
            ]
        );
    }

    #[test]
    fn capture_args_default_to_no_game_flag() {
        assert_eq!(
            capture_args(None),
            vec!["-m", "companion.api", "capture"]
                .iter()
                .map(|s| s.to_string())
                .collect::<Vec<_>>()
        );
    }

    #[test]
    fn capture_args_pass_explicit_game() {
        assert_eq!(
            capture_args(Some("witcher3")),
            vec![
                "-m".to_string(),
                "companion.api".to_string(),
                "capture".to_string(),
                "--game".to_string(),
                "witcher3".to_string(),
            ]
        );
    }

    #[test]
    fn analyze_args_without_game_omit_flag() {
        let args = analyze_args("x.png", "q", None, false);
        assert!(!args.contains(&"--game".to_string()));
        assert!(!args.contains(&"--context".to_string()));
    }

    #[test]
    fn analyze_args_with_context_adds_stdin_marker() {
        let args = analyze_args("x.png", "q", Some("witcher3"), true);
        let tail = &args[args.len() - 2..];
        assert_eq!(tail, &["--context".to_string(), "-".to_string()]);
    }

    #[test]
    fn session_turns_roundtrip_with_unicode() {
        let turns = vec![SessionTurn {
            game_id: "witcher3".to_string(),
            question: "Et le Seigneur d'Undvik ?".to_string(),
            answer: "Éminemment.".to_string(),
        }];
        let json = serde_json::to_string(&turns).expect("serializes");
        assert!(json.contains("Undvik"));
        let parsed: Vec<SessionTurn> = serde_json::from_str(&json).expect("parses");
        assert_eq!(parsed, turns);
    }

    // Subprocess regression tests: these exercise the REAL spawn path
    // (`execute_with_optional_stdin`), which is where a stdout-capture
    // bug previously escaped the args/parsing-only tests.

    #[cfg(windows)]
    #[test]
    fn subprocess_stdout_is_captured_without_stdin_payload() {
        let mut command = Command::new("cmd");
        command.args(["/C", "echo gamesage-bridge-ok"]);

        let output = execute_with_optional_stdin(command, None).expect("subprocess runs");

        assert!(output.status.success());
        assert!(
            String::from_utf8_lossy(&output.stdout).contains("gamesage-bridge-ok"),
            "stdout must be captured when no stdin payload exists"
        );
    }

    #[cfg(windows)]
    #[test]
    fn subprocess_stdout_is_captured_with_stdin_payload() {
        // Round-trip through the repository dev Python: it echoes stdin
        // back on stdout, proving the payload is written AND stdout is
        // still captured in the stdin path.
        let python = repo_root().join(".venv").join("Scripts").join("python.exe");
        if !python.is_file() {
            eprintln!("skipping: repository .venv python not found");
            return;
        }
        let mut command = Command::new(&python);
        command.args(["-c", "import sys; sys.stdout.write(sys.stdin.read())"]);
        let payload = "{\"question\": \"Et le Seigneur d'Undvik ?\", \"answer\": \"Éminemment.\"}";

        let output =
            execute_with_optional_stdin(command, Some(payload.to_string())).expect("subprocess runs");

        assert!(output.status.success());
        assert_eq!(
            String::from_utf8_lossy(&output.stdout),
            payload,
            "stdout must be captured and the Unicode stdin payload delivered intact"
        );
    }

    #[cfg(windows)]
    #[test]
    fn exit_zero_with_empty_stdout_yields_backend_error() {
        // A successful process that prints nothing must produce the
        // existing diagnostic — not an empty success.
        let mut command = Command::new("cmd");
        command.args(["/C", "exit", "0"]);

        let output = execute_with_optional_stdin(command, None).expect("subprocess runs");

        let error = stdout_or_backend_error(output).expect_err("empty stdout must fail");
        assert_eq!(error.code, "invalid_backend_response");
        assert!(error.message.contains("without producing a response"));
    }

    #[cfg(windows)]
    #[test]
    fn real_python_games_call_round_trips_through_the_bridge() {
        // End-to-end guard on the exact startup call that regressed.
        let stdout = run_python(&games_args()).expect("games call succeeds");
        let response = parse_games_envelope(&stdout).expect("valid envelope");
        assert!(!response.games.is_empty());
        assert_eq!(response.default_game, "witcher3");
    }

    #[test]
    fn parses_games_envelope() {
        let stdout = r#"{"ok": true, "games": [{"id": "witcher3", "display_name": "The Witcher 3: Wild Hunt", "origin": "native"}], "default_game": "witcher3"}"#;
        let response = parse_games_envelope(stdout).expect("valid envelope");
        assert_eq!(response.default_game, "witcher3");
        assert_eq!(
            response.games,
            vec![GameInfo {
                id: "witcher3".to_string(),
                display_name: "The Witcher 3: Wild Hunt".to_string(),
                origin: Some("native".to_string()),
            }]
        );
    }

    #[test]
    fn parses_games_envelope_without_origin_for_backward_compatibility() {
        let stdout = r#"{"ok": true, "games": [{"id": "bg3", "display_name": "Baldur's Gate 3"}], "default_game": "bg3"}"#;
        let response = parse_games_envelope(stdout).expect("valid envelope");
        assert_eq!(response.games[0].origin, None);
    }

    #[test]
    fn games_envelope_rejects_invalid_payloads() {
        assert_eq!(
            parse_games_envelope("not json").unwrap_err().code,
            "invalid_backend_response"
        );
        assert_eq!(
            parse_games_envelope(r#"{"ok": false}"#).unwrap_err().code,
            "invalid_backend_response"
        );
        assert_eq!(
            parse_games_envelope(r#"{"ok": true, "games": []}"#)
                .unwrap_err()
                .code,
            "invalid_backend_response"
        );
    }

    #[test]
    fn parses_community_content_envelope() {
        let stdout = r#"{
            "ok": true,
            "games": [
                {"id": "witcher3", "display_name": "The Witcher 3: Wild Hunt", "origin": "native"},
                {"id": "demo_game", "display_name": "Demo Game", "origin": "community",
                 "definition_id": "author.demo.windows", "version": "1.0.0", "author": "Author"}
            ],
            "game_definitions": [
                {"definition_id": "author.demo.windows", "status": "loaded", "message": "ok",
                 "game_id": "demo_game", "display_name": "Demo Game", "version": "1.0.0", "author": "Author"},
                {"definition_id": "broken.dir", "status": "invalid",
                 "message": "corpus.jsonl line 2: invalid JSON", "game_id": null,
                 "display_name": null, "version": null, "author": null}
            ],
            "knowledge_packs": [
                {"pack_id": "gamesage.witcher3.starter", "status": "loaded",
                 "message": "5 records", "game_id": "witcher3",
                 "name": "Starter", "version": "1.0.0", "author": "GameSage",
                 "languages": ["en"], "record_count": 5},
                {"pack_id": "broken.pack", "status": "invalid",
                 "message": "corpus.jsonl line 182: missing required field(s): text",
                 "game_id": "witcher3", "name": "Broken", "version": "2.0.0",
                 "author": "X", "languages": null, "record_count": null}
            ]
        }"#;
        let content = parse_community_envelope(stdout).expect("valid envelope");
        assert_eq!(content.games.len(), 2);
        assert_eq!(content.games[1].origin, "community");
        assert_eq!(content.games[1].definition_id.as_deref(), Some("author.demo.windows"));
        assert_eq!(content.game_definitions.len(), 2);
        assert_eq!(content.game_definitions[1].status, "invalid");
        assert!(content.game_definitions[1].game_id.is_none());
        assert_eq!(content.knowledge_packs.len(), 2);
        assert_eq!(content.knowledge_packs[0].record_count, Some(5));
        assert_eq!(content.knowledge_packs[0].languages, Some(vec!["en".to_string()]));
        assert!(content.knowledge_packs[1].record_count.is_none());
    }

    #[test]
    fn community_content_rejects_invalid_payloads() {
        assert_eq!(
            parse_community_envelope("not json").unwrap_err().code,
            "invalid_backend_response"
        );
        assert_eq!(
            parse_community_envelope(r#"{"ok": false}"#).unwrap_err().code,
            "invalid_backend_response"
        );
        assert_eq!(
            parse_community_envelope(r#"{"ok": true, "games": []}"#)
                .unwrap_err()
                .code,
            "invalid_backend_response"
        );
    }
}

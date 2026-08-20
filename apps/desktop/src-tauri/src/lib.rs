mod bridge;

use tauri::{Emitter, RunEvent};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutEvent, ShortcutState};

/// Global capture shortcut for the desktop app.
///
/// Mirrors the standalone Python listener default in
/// `companion/games/witcher3/hotkey.py` (`DEFAULT_HOTKEY`).
pub const CAPTURE_SHORTCUT: &str = "ctrl+f8";

/// Event emitted to the frontend when the global shortcut is pressed.
pub const CAPTURE_REQUESTED_EVENT: &str = "capture-requested";

fn handle_capture_shortcut(app: &tauri::AppHandle, _shortcut: &Shortcut, event: ShortcutEvent) {
    if event.state != ShortcutState::Pressed {
        return; // Trigger on press only, not on release.
    }
    // The frontend owns the capture state machine; this event feeds the
    // exact same flow as the "Capture Game" button.
    if let Err(error) = app.emit(CAPTURE_REQUESTED_EVENT, ()) {
        eprintln!("gamesage: could not emit {CAPTURE_REQUESTED_EVENT}: {error}");
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            match app
                .global_shortcut()
                .on_shortcut(CAPTURE_SHORTCUT, handle_capture_shortcut)
            {
                Ok(()) => println!("gamesage: global shortcut {CAPTURE_SHORTCUT} registered"),
                Err(error) => eprintln!(
                    "gamesage: could not register global shortcut {CAPTURE_SHORTCUT}: {error}; \
                     the Capture Game button still works"
                ),
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bridge::capture_game,
            bridge::analyze_game
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Err(error) = app.global_shortcut().unregister_all() {
                    eprintln!("gamesage: could not unregister shortcuts on exit: {error}");
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capture_shortcut_stays_ctrl_f8_and_parses() {
        assert_eq!(CAPTURE_SHORTCUT, "ctrl+f8");
        assert!(
            Shortcut::try_from(CAPTURE_SHORTCUT).is_ok(),
            "CAPTURE_SHORTCUT must be parseable by the global-shortcut plugin"
        );
    }
}

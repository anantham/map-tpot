/**
 * Settings.jsx — BYOK (Bring Your Own Key) settings modal + icon button.
 *
 * Allows users to store an OpenRouter API key in localStorage
 * for direct card generation without hitting the serverless budget.
 */

import { useState, useEffect, useCallback } from "react";

const LOCALSTORAGE_KEY = "openrouter_key";

/**
 * Small gear icon button for the header area.
 * Shows a green dot badge when a BYOK key is stored.
 */
export function SettingsIcon({ onClick }) {
  const [hasKey, setHasKey] = useState(false);

  useEffect(() => {
    try {
      setHasKey(!!localStorage.getItem(LOCALSTORAGE_KEY));
    } catch {
      // localStorage unavailable
    }
  }, []);

  // Re-check on focus (user may have changed key in another tab)
  useEffect(() => {
    const check = () => {
      try {
        setHasKey(!!localStorage.getItem(LOCALSTORAGE_KEY));
      } catch {}
    };
    window.addEventListener("focus", check);
    return () => window.removeEventListener("focus", check);
  }, []);

  return (
    <button
      className="settings-icon-btn"
      onClick={onClick}
      title="API Key Settings"
      aria-label="Settings"
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
      {hasKey && <span className="settings-dot" />}
    </button>
  );
}

/**
 * Settings modal overlay with API key management.
 */
export default function Settings({ open, onClose }) {
  const [keyValue, setKeyValue] = useState("");
  const [saved, setSaved] = useState(false);

  // Load current key state on open
  useEffect(() => {
    if (open) {
      try {
        const existing = localStorage.getItem(LOCALSTORAGE_KEY);
        setSaved(!!existing);
        setKeyValue(""); // never pre-fill the key for security
      } catch {
        setSaved(false);
      }
    }
  }, [open]);

  const handleSave = useCallback(() => {
    const trimmed = keyValue.trim();
    if (!trimmed) return;

    try {
      localStorage.setItem(LOCALSTORAGE_KEY, trimmed);
      setSaved(true);
      setKeyValue("");
    } catch (err) {
      console.error("[Settings] Failed to save key:", err);
    }
  }, [keyValue]);

  const handleClear = useCallback(() => {
    try {
      localStorage.removeItem(LOCALSTORAGE_KEY);
      setSaved(false);
      setKeyValue("");
    } catch (err) {
      console.error("[Settings] Failed to clear key:", err);
    }
  }, []);

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === "Enter") handleSave();
      if (e.key === "Escape") onClose();
    },
    [handleSave, onClose]
  );

  if (!open) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        <h3>API Key Settings</h3>

        <p className="settings-description">
          Add your own{" "}
          <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer">
            OpenRouter API key
          </a>{" "}
          to generate cards without limits. Your key is stored locally and never sent to our server.
        </p>

        {saved ? (
          <div className="settings-saved-state">
            <span className="settings-status">Using your key</span>
            <button className="settings-clear-btn" onClick={handleClear}>
              Clear key
            </button>
          </div>
        ) : (
          <div className="settings-input-row">
            <input
              type="password"
              className="settings-key-input"
              placeholder="sk-or-v1-..."
              value={keyValue}
              onChange={(e) => setKeyValue(e.target.value)}
              onKeyDown={handleKeyDown}
              autoFocus
            />
            <button
              className="settings-save-btn"
              onClick={handleSave}
              disabled={!keyValue.trim()}
            >
              Save
            </button>
          </div>
        )}

        <button className="settings-close-btn" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}

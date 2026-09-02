"""Стили и общие виджеты интерфейса — тёплый стол, не админка Streamlit."""

from __future__ import annotations

import re

import streamlit as st

from ui.api_client import api_get, api_post, friendly_error, vk_is_configured

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&family=Source+Sans+3:wght@400;500;600&display=swap');

:root {
  --ink: #3d3229;
  --muted: #7a6a5c;
  --line: #e6dcd0;
  --bg: #FAF8F5;
  --panel: #fffaf4;
  --panel-2: #fbf5ee;
  --accent: #8B7355;
  --accent-hover: #6f5b43;
  --soft: #f4eee7;
  --shadow: 0 8px 22px rgba(139, 115, 85, 0.05);
  --shadow-lg: 0 14px 36px rgba(139, 115, 85, 0.08);
  --radius: 14px;
  --radius-sm: 10px;
  --radius-lg: 18px;
  color-scheme: light;
}

html {
  color-scheme: light only;
}

html, body, .stApp, [data-testid="stAppViewContainer"] {
  background: var(--bg) !important;
  color: var(--ink);
  font-family: "Source Sans 3", "Segoe UI", sans-serif !important;
}

[data-testid="stHeader"] {
  background: transparent !important;
  height: 0 !important;
  min-height: 0 !important;
}
/* Шапка нужна, когда сайдбар свёрнут — иначе на телефоне не открыть стол */
[data-testid="stHeader"]:has([data-testid="stExpandSidebarButton"]) {
  height: 3.6rem !important;
  background: var(--bg) !important;
  border-bottom: 1px solid var(--line);
}
#MainMenu, footer,
[data-testid="stDecoration"], [data-testid="stStatusWidget"],
.stDeployButton, div[data-testid="stAppDeployButton"] {
  display: none !important;
}
[data-testid="stToolbar"] {
  display: none !important;
}
[data-testid="stHeader"]:has([data-testid="stExpandSidebarButton"]) [data-testid="stToolbar"] {
  display: flex !important;
  align-items: center !important;
  height: 100% !important;
  padding-left: 0.55rem !important;
}
[data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"] {
  display: none !important;
}
[data-testid="stExpandSidebarButton"] {
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  width: auto !important;
  min-width: 2.75rem !important;
  min-height: 2.6rem !important;
  height: 2.6rem !important;
  padding: 0 0.9rem 0 0.75rem !important;
  gap: 0.5rem !important;
  background: var(--panel) !important;
  border: 1px solid var(--line) !important;
  border-radius: 10px !important;
  color: var(--ink) !important;
  box-shadow: 0 4px 14px rgba(139, 115, 85, 0.08) !important;
}
[data-testid="stExpandSidebarButton"] > * {
  display: none !important;
}
[data-testid="stExpandSidebarButton"]::before {
  content: "";
  width: 1.05rem;
  height: 2px;
  background: currentColor;
  box-shadow: 0 -5px currentColor, 0 5px currentColor;
}
[data-testid="stExpandSidebarButton"]::after {
  content: "меню";
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
  font-size: 0.95rem;
  font-weight: 500;
}
/* На широком экране сайдбар не прячем — кнопка «закрыть» только мешает */
@media (min-width: 768px) {
  [data-testid="stSidebarCollapseButton"] {
    display: none !important;
  }
}
[data-testid="stSidebarCollapseButton"] button {
  min-width: 2.4rem !important;
  min-height: 2.4rem !important;
  width: auto !important;
  padding: 0 0.75rem !important;
  background: transparent !important;
  border: 1px solid var(--line) !important;
  border-radius: 8px !important;
  color: var(--ink) !important;
}
[data-testid="stSidebarCollapseButton"] button > * {
  display: none !important;
}
[data-testid="stSidebarCollapseButton"] button::after {
  content: "меню";
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--ink);
}

.block-container {
  padding-top: 1.2rem !important;
  padding-bottom: 6.5rem !important;
  max-width: 740px !important;
}

h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
  font-family: "Source Serif 4", Georgia, "Times New Roman", serif !important;
  color: var(--ink) !important;
  font-weight: 500 !important;
  letter-spacing: -0.015em;
}

/* Сайдбар — тихий рельс как у Claude */
[data-testid="stSidebar"] {
  background: #f3ebe3 !important;
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] .block-container {
  padding-top: 1.2rem !important;
  padding-bottom: 1.5rem !important;
}
[data-testid="stSidebar"] * {
  font-family: "Source Sans 3", "Segoe UI", sans-serif !important;
}
.tr-side-brand {
  font-family: "Source Serif 4", Georgia, serif !important;
  font-size: 1.2rem;
  font-weight: 500;
  color: var(--ink);
  margin: 0 0 0.15rem 0;
}
.tr-side-sub {
  color: var(--muted);
  font-size: 0.85rem;
  margin: 0 0 1rem 0;
}
.tr-side-label {
  color: var(--muted);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0.85rem 0 0.35rem 0;
}
[data-testid="stSidebar"] .stButton > button {
  border-radius: 8px !important;
  justify-content: flex-start !important;
  text-align: left !important;
  font-weight: 500 !important;
  padding: 0.45rem 0.75rem !important;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"],
[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="baseButton-secondary"] {
  background: transparent !important;
  border: 1px solid transparent !important;
  color: var(--ink) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
  background: var(--soft) !important;
  border-color: var(--line) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: #e8ddd0 !important;
  border-color: #d9cbb8 !important;
  color: var(--ink) !important;
}

/* Empty chat home — Claude-like */
.tr-chat-home {
  text-align: center;
  padding: 4.5rem 1rem 1.5rem;
}
.tr-chat-home-title {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.75rem;
  font-weight: 500;
  color: var(--ink);
  margin: 0 0 0.4rem 0;
}
.tr-chat-home-sub {
  color: var(--muted);
  font-size: 1.05rem;
  margin: 0 0 1.6rem 0;
}

/* Сообщения и поле ввода */
[data-testid="stChatMessage"] {
  background: transparent !important;
  padding: 0.35rem 0 !important;
}
[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] {
  background: transparent !important;
  border: none !important;
  padding: 0.15rem 0 !important;
}
[data-testid="stChatMessageAvatar"],
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatAvatar"],
[data-testid="stChatMessage"] [data-testid="stImage"] {
  display: none !important;
}
[data-testid="stChatInput"] {
  background: var(--bg) !important;
}
[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"],
[data-testid="stChatInputContainer"] {
  background: var(--bg) !important;
  border-top: 1px solid var(--line) !important;
}
[data-testid="stChatInput"] textarea {
  border-radius: var(--radius) !important;
  border-color: var(--line) !important;
  background: var(--panel) !important;
  font-size: 1rem !important;
  color: var(--ink) !important;
}
[data-testid="stChatInput"] textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px rgba(139, 115, 85, 0.12) !important;
}

.tr-desk-back {
  margin: 0 0 0.85rem 0;
}

/* Карточки Streamlit 1.4+ */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--panel) !important;
  border: 1px solid var(--line) !important;
  border-radius: var(--radius) !important;
  box-shadow: none !important;
  padding: 0.05rem 0.1rem;
  margin: 0.35rem 0 0.55rem !important;
}

.tr-brand {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.55rem;
  color: var(--ink);
  margin: 0 0 0.15rem 0;
  font-weight: 500;
}
.tr-brand-sub {
  color: var(--muted);
  font-size: 0.95rem;
  margin: 0 0 1.1rem 0;
}

.tr-why {
  margin-top: 0.45rem;
  padding: 0;
  background: transparent;
  border: none;
  font-size: 0.82rem;
  line-height: 1.4;
  color: var(--muted);
}
.tr-why strong {
  color: var(--ink);
  font-weight: 600;
}
.tr-chat-foot {
  margin-top: 0.25rem;
}

.tr-think {
  margin: 0 0 0.9rem 0;
  padding: 1rem 1.15rem 1.05rem;
  background: var(--soft);
  border-radius: var(--radius);
  border-left: 3px solid var(--accent);
  color: var(--muted);
  max-height: 18rem;
  overflow-y: auto;
}
.tr-think-kicker {
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 0.55rem 0;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.tr-think-kicker::before {
  content: "";
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  background: var(--accent);
  display: inline-block;
}
.tr-think-body, .tr-think > p {
  font-family: "Source Serif 4", Georgia, serif;
  font-style: italic;
  font-size: 1.02rem;
  line-height: 1.62;
  margin: 0;
  color: var(--ink);
}
@keyframes tr-breathe {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 1; }
}
@keyframes tr-dot-pulse {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.45; }
  40% { transform: scale(1); opacity: 1; }
}
.tr-think-wait .tr-think-kicker {
  animation: tr-breathe 2.8s ease-in-out infinite;
}
.tr-think-wait .tr-think-kicker::before {
  animation: tr-dot-pulse 1.4s ease-in-out infinite;
}
.tr-think-hint {
  margin-top: 0.4rem;
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 0.95rem;
  font-style: italic;
  line-height: 1.5;
  color: var(--muted);
}
.tr-voice {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 1.35rem 1.4rem 1.2rem;
  margin: 0.9rem 0 1.3rem;
  box-shadow: var(--shadow);
}
.tr-voice-kicker {
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 0.35rem 0;
}
.tr-voice-title {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.45rem;
  font-weight: 500;
  color: var(--ink);
  margin: 0 0 0.85rem 0;
  letter-spacing: -0.02em;
}
.tr-voice-lead {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.08rem;
  line-height: 1.65;
  color: var(--ink);
  margin: 0 0 1rem 0;
}
.tr-voice-body {
  font-size: 0.95rem;
  line-height: 1.55;
  color: var(--muted);
  margin: 0 0 0.85rem 0;
}
.tr-voice-label {
  display: block;
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 0.25rem 0;
}
.tr-voice-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.85rem 1.1rem;
  margin: 0.4rem 0 1rem;
}
@media (max-width: 640px) {
  .tr-voice-grid { grid-template-columns: 1fr; }
}
.tr-voice-shade {
  background: var(--soft);
  border-radius: 12px;
  padding: 0.75rem 0.85rem;
}
.tr-voice-shade-t {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.02rem;
  color: var(--ink);
  margin: 0 0 0.35rem 0;
}
.tr-voice-shade p {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.5;
  color: var(--muted);
}
.tr-voice-quote {
  margin: 0.45rem 0;
  padding: 0.15rem 0 0.15rem 0.9rem;
  border-left: 2px solid var(--accent);
  font-family: "Source Serif 4", Georgia, serif;
  font-style: italic;
  font-size: 1.02rem;
  line-height: 1.5;
  color: var(--ink);
}
.tr-voice-words, .tr-voice-not {
  font-size: 0.86rem;
  line-height: 1.5;
  color: var(--muted);
  margin: 0.7rem 0 0;
}
.tr-empty {
  padding: 2rem 1rem;
  text-align: center;
  color: var(--muted);
  font-size: 1.05rem;
  line-height: 1.65;
  font-family: "Source Serif 4", Georgia, serif;
  background: var(--panel);
  border: 1px dashed var(--line);
  border-radius: var(--radius);
  margin: 0.8rem 0 1.2rem;
}
.tr-empty-icon {
  display: block;
  font-size: 1.7rem;
  margin-bottom: 0.4rem;
  opacity: 0.45;
}
[data-testid="stFileUploaderDropzoneInstructions"] span {
  font-size: 0 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"]::after {
  content: "перетащи кадр или выбери файл";
  font-size: 0.92rem !important;
  color: var(--muted);
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
}
[data-testid="stFileUploader"] small {
  display: none !important;
}
[data-testid="stFileUploaderDropzone"] {
  background: var(--panel) !important;
  border-color: var(--line) !important;
  border-radius: var(--radius) !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
  border-color: var(--accent) !important;
  background: var(--soft) !important;
}

/* Чипы и сетки */
.tr-chip {
  display: block;
  background: var(--soft);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 0.45rem 0.5rem;
  margin: 0.25rem 0;
  font-size: 0.82rem;
  line-height: 1.3;
  color: var(--ink);
  text-align: left;
}
.tr-day {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 0.8rem;
  color: var(--muted);
  text-align: center;
  margin-bottom: 0.35rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid var(--line);
}
.tr-day--today {
  color: var(--accent);
  font-weight: 600;
}

/* Прогресс-бар онбординга */
.tr-progress {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 1.4rem 0;
}
.tr-progress-step {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.82rem;
  color: var(--muted);
  font-family: "Source Sans 3", sans-serif;
}
.tr-progress-dot {
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  background: var(--line);
  display: inline-block;
  transition: background 0.2s ease, transform 0.2s ease;
}
.tr-progress-step.is-active .tr-progress-dot {
  background: var(--accent);
  transform: scale(1.25);
}
.tr-progress-step.is-done .tr-progress-dot {
  background: var(--accent);
}
.tr-progress-step.is-done {
  color: var(--ink);
}
.tr-progress-step.is-active {
  color: var(--ink);
  font-weight: 500;
}
.tr-progress-line {
  flex: 1;
  height: 1px;
  background: var(--line);
  margin: 0 0.25rem;
}

/* Адаптивная сетка чипов на главной чата */
.tr-chips-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.6rem;
  margin: 1.2rem 0 0.5rem;
}
@media (min-width: 640px) {
  .tr-chips-grid { grid-template-columns: repeat(4, 1fr); }
}
.tr-chips-grid .stButton > button {
  background: var(--panel) !important;
  border: 1px solid var(--line) !important;
  color: var(--ink) !important;
  border-radius: var(--radius-sm) !important;
  padding: 0.7rem 0.5rem !important;
  font-size: 0.92rem !important;
  font-weight: 500 !important;
  transition: all 0.15s ease;
}
.tr-chips-grid .stButton > button:hover {
  background: var(--soft) !important;
  border-color: var(--accent) !important;
  color: var(--accent-hover) !important;
  transform: translateY(-1px);
}

/* Pending prefill — карточка черновика над полем ввода */
.tr-pending {
  background: var(--panel);
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  padding: 0.85rem 1rem;
  margin: 0.6rem 0 1rem;
  box-shadow: var(--shadow);
}
.tr-pending-kicker {
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 0.4rem 0;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.tr-pending-kicker::before {
  content: "✎";
  font-size: 0.85rem;
}
.tr-pending-body {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1rem;
  line-height: 1.55;
  color: var(--ink);
  white-space: pre-wrap;
  max-height: 12rem;
  overflow-y: auto;
  margin: 0 0 0.7rem 0;
}

/* Счётчик символов */
.tr-counter {
  font-family: "Source Sans 3", sans-serif;
  font-size: 0.75rem;
  color: var(--muted);
  text-align: right;
  margin: -0.4rem 0 0.6rem 0;
}
.tr-counter--warn { color: var(--accent); }

/* Кнопка копирования */
.tr-copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--soft);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
  color: var(--ink);
  cursor: pointer;
  font-family: "Source Sans 3", sans-serif;
  transition: all 0.15s ease;
}
.tr-copy-btn:hover {
  background: var(--panel);
  border-color: var(--accent);
  color: var(--accent-hover);
}
.tr-copy-btn--done {
  background: var(--accent) !important;
  color: var(--bg) !important;
  border-color: var(--accent) !important;
}

/* Сегментированный контроль (для аналитики и т.д.) */
.tr-segmented {
  display: inline-flex;
  background: var(--soft);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 0.2rem;
  gap: 0.15rem;
  margin: 0.4rem 0 1rem;
}
.tr-segmented .stButton > button {
  background: transparent !important;
  border: none !important;
  color: var(--muted) !important;
  padding: 0.35rem 0.9rem !important;
  border-radius: 8px !important;
  font-size: 0.88rem !important;
  font-weight: 500 !important;
  box-shadow: none !important;
}
.tr-segmented .stButton > button:hover {
  background: var(--panel) !important;
  color: var(--ink) !important;
}
.tr-segmented .stButton > button[kind="primary"] {
  background: var(--panel) !important;
  color: var(--ink) !important;
  box-shadow: var(--shadow) !important;
}

/* Адаптивная сетка недели */
.tr-week-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 0.4rem;
  margin: 0.4rem 0 1rem;
}
@media (max-width: 720px) {
  .tr-week-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 380px) {
  .tr-week-grid { grid-template-columns: 1fr; }
}
.tr-week-col {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 0.4rem 0.4rem 0.55rem;
  min-height: 4rem;
}
.tr-week-col--today {
  border-color: var(--accent);
  background: var(--soft);
}

/* Превью фото — адаптивное */
.tr-photo-grid {
  display: grid;
  gap: 0.5rem;
  margin: 0.5rem 0 1rem;
}
.tr-photo-grid[data-count="1"] { grid-template-columns: 1fr; max-width: 320px; }
.tr-photo-grid[data-count="2"] { grid-template-columns: repeat(2, 1fr); }
.tr-photo-grid[data-count="3"] { grid-template-columns: repeat(3, 1fr); }
.tr-photo-grid[data-count="4"] { grid-template-columns: repeat(2, 1fr); }
.tr-photo-grid[data-count="5"], .tr-photo-grid[data-count="6"] { grid-template-columns: repeat(3, 1fr); }
.tr-photo-grid[data-count="7"], .tr-photo-grid[data-count="8"] { grid-template-columns: repeat(4, 1fr); }
@media (max-width: 540px) {
  .tr-photo-grid[data-count="3"],
  .tr-photo-grid[data-count="5"],
  .tr-photo-grid[data-count="6"],
  .tr-photo-grid[data-count="7"],
  .tr-photo-grid[data-count="8"] { grid-template-columns: repeat(2, 1fr); }
}

/* Тихая кнопка удаления */
.tr-danger-btn .stButton > button {
  color: #b54848 !important;
  border-color: rgba(181, 72, 72, 0.3) !important;
  background: transparent !important;
}
.tr-danger-btn .stButton > button:hover {
  background: rgba(181, 72, 72, 0.08) !important;
  border-color: #b54848 !important;
}

/* Тост после успеха (вместо st.success перед rerun) */
.tr-toast {
  position: fixed;
  bottom: 5rem;
  left: 50%;
  transform: translateX(-50%);
  background: var(--ink);
  color: var(--bg);
  padding: 0.7rem 1.2rem;
  border-radius: 999px;
  font-family: "Source Sans 3", sans-serif;
  font-size: 0.92rem;
  box-shadow: var(--shadow-lg);
  z-index: 1000;
  animation: tr-toast-in 0.25s ease;
  max-width: 90vw;
  text-align: center;
}
@keyframes tr-toast-in {
  from { opacity: 0; transform: translate(-50%, 10px); }
  to { opacity: 1; transform: translate(-50%, 0); }
}

/* Кнопки: основные и тихие */
.stButton > button {
  background: var(--accent) !important;
  color: var(--bg) !important;
  border: 1px solid var(--accent) !important;
  border-radius: var(--radius-sm) !important;
  padding: 0.38rem 0.9rem !important;
  font-weight: 500 !important;
  box-shadow: none !important;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease;
}
.stButton > button:hover {
  background: var(--accent-hover) !important;
  border-color: var(--accent-hover) !important;
  color: var(--bg) !important;
}
.stButton > button:active {
  transform: translateY(1px);
}
.stButton > button:disabled {
  opacity: 0.5 !important;
  cursor: not-allowed;
}
.stButton > button[kind="secondary"],
div[data-testid="stButton"] button[data-testid="baseButton-secondary"] {
  background: transparent !important;
  color: var(--accent) !important;
  border: 1px solid var(--line) !important;
}
.stButton > button[kind="secondary"]:hover,
div[data-testid="stButton"] button[data-testid="baseButton-secondary"]:hover {
  background: var(--soft) !important;
  border-color: var(--accent) !important;
  color: var(--accent-hover) !important;
}

div[data-testid="stMetric"] {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 0.55rem 0.7rem;
  transition: border-color 0.15s ease;
}
div[data-testid="stMetric"]:hover {
  border-color: var(--accent);
}
div[data-testid="stMetric"] label {
  color: var(--muted) !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
  color: var(--ink) !important;
}

textarea, input, [data-baseweb="input"], [data-baseweb="textarea"],
[data-baseweb="select"] > div {
  border-radius: var(--radius-sm) !important;
  border-color: var(--line) !important;
  background: var(--panel) !important;
  color: var(--ink) !important;
}
textarea:focus, input:focus, [data-baseweb="input"]:focus, [data-baseweb="textarea"]:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px rgba(139, 115, 85, 0.12) !important;
}
[data-baseweb="select"] > div > div {
  color: var(--ink) !important;
}

[data-testid="stExpander"] {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  margin: 0.4rem 0;
}
div[data-testid="stAlert"] {
  border-radius: 12px !important;
}

hr {
  border: none;
  border-top: 1px solid var(--line);
  margin: 1.1rem 0;
}

/* Утилита для скрытия label */
.tr-hidden-label [data-testid="stWidgetLabel"] {
  display: none !important;
}

/* Дельта-карточка сравнения периодов */
.tr-delta {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 0.7rem 0.85rem;
  margin: 0.25rem 0;
}
.tr-delta-label {
  font-size: 0.78rem;
  color: var(--muted);
  margin: 0 0 0.2rem 0;
  font-family: "Source Sans 3", sans-serif;
}
.tr-delta-value {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.15rem;
  color: var(--ink);
}
.tr-delta-pct {
  font-size: 0.85rem;
  margin-left: 0.4rem;
  font-weight: 600;
}
.tr-delta-up { color: #4a8a4a; }
.tr-delta-down { color: #b54848; }
.tr-delta-flat { color: var(--muted); }

/* Стат-плашка (мини) */
.tr-stat {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.7rem 0.9rem;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  margin: 0.3rem 0;
}
.tr-stat-label {
  font-size: 0.74rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-family: "Source Sans 3", sans-serif;
}
.tr-stat-value {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.4rem;
  color: var(--ink);
  line-height: 1.1;
}
</style>
"""


def inject_theme() -> None:
    # Streamlit 1.62: <style> через markdown часто не садится — остаётся голый каркас.
    html = getattr(st, "html", None)
    if callable(html):
        html(CSS)
    else:
        st.markdown(CSS, unsafe_allow_html=True)


def brand_header(subtitle: str = "ассистент, не автор") -> None:
    st.markdown(
        f'<div class="tr-brand">Тихая редакция</div>'
        f'<p class="tr-brand-sub">{subtitle}</p>',
        unsafe_allow_html=True,
    )


def toast(message: str, *, duration_seconds: float = 2.5) -> None:
    """Тихий тост вместо st.success + st.rerun (которая убивала сообщение)."""
    ms = int(duration_seconds * 1000)
    st.markdown(
        f'<div class="tr-toast" id="tr-toast-{id(message)}">{message}</div>'
        f'<script>setTimeout(function(){{var e=document.getElementById("tr-toast-{id(message)}");'
        f"if(e){{e.style.transition='opacity 0.3s';e.style.opacity='0';"
        f"setTimeout(function(){{e.remove();}},300);}}}},{ms});</script>",
        unsafe_allow_html=True,
    )


def desk_back_to_chat() -> None:
    """Возврат со стола в диалог (Claude-like: инструменты вторичны)."""
    if st.button("← к диалогу", type="secondary", key="desk_back"):
        st.session_state["nav_to"] = "Чат"
        st.rerun()


def why_block(why: dict | None) -> None:
    if not why:
        return
    related = why.get("related_posts") or []
    cites: list[str] = []
    for item in related[:3]:
        found = re.search(r"#\d+", str(item))
        if found:
            cites.append(found.group(0))
    summary = re.sub(r"\s+", " ", (why.get("summary") or "").strip())
    if len(summary) > 110:
        summary = summary[:107].rstrip() + "…"
    bits = [b for b in (summary, " · ".join(cites)) if b]
    if not bits:
        return
    st.markdown(
        f'<div class="tr-why"><strong>Почему</strong> · {" · ".join(bits)}</div>',
        unsafe_allow_html=True,
    )


def archive_paste_widget(*, key: str, min_blocks: int = 2) -> None:
    """Вставка своих постов — на знакомстве и позже."""
    pasted = st.text_area(
        "Свои посты",
        placeholder="Пост 1:\n...\n\nПост 2:\n...",
        height=200,
        key=f"{key}_pasted",
    )
    if st.button("сохранить в память", key=f"{key}_save"):
        blocks = [b.strip() for b in pasted.split("\n\n") if b.strip()]
        if len(blocks) < min_blocks:
            st.warning(
                "Нужно хотя бы два блока — так я лучше чувствую голос."
                if min_blocks > 1
                else "Нужен хотя бы один пост."
            )
            return
        try:
            with st.spinner("сохраняю…"):
                api_post("/onboarding/archive", json={"posts": blocks})
        except Exception as exc:
            friendly_error(exc)
            return
        # Тост проживёт один rerun: кладём в session и снимаем после.
        st.session_state["_toast"] = "Тексты в памяти. Голос дособирается тихо 🤍"
        st.rerun()


def archive_needed_banner() -> None:
    """Если архив пуст — сначала стена VK, вставка руками только запасной путь."""
    # Сначала показать тост, если он есть в session — и не снимать его сразу
    _toast_pending = st.session_state.pop("_toast", None)
    if _toast_pending:
        toast(_toast_pending)

    try:
        status = api_get("/onboarding/status")
    except Exception as exc:
        friendly_error(exc)
        return
    posts_n = int(status.get("posts_imported") or 0)
    if posts_n >= 2:
        return

    vk_ok = vk_is_configured()
    if vk_ok:
        empty_state(
            "В памяти ещё нет твоих постов. Загрузи со стены VK — так редакция узнает "
            "голос и сообщество. Вставка руками нужна только если стена недоступна."
        )
        if st.session_state.get("vk_wall_error"):
            st.error(st.session_state["vk_wall_error"])
        if st.button("загрузить посты со стены VK", key="dash_import_vk"):
            try:
                with st.spinner("читаю стену…"):
                    api_post("/onboarding/import-vk")
                st.session_state.pop("vk_wall_error", None)
                st.session_state["_toast"] = "Посты в памяти. Голос дособирается тихо 🤍"
                st.rerun()
            except Exception as exc:
                from ui.api_client import ApiError

                msg = (
                    exc.message
                    if isinstance(exc, ApiError)
                    else "Не получилось загрузить стену. Можно вставить тексты вручную."
                )
                st.session_state["vk_wall_error"] = msg
                st.error(msg)
        with st.expander("Вставить тексты вручную", expanded=False):
            st.caption(
                "Если со стены не получается (ограничения доступа) — "
                "вставь 3–8 своих постов ниже."
            )
            archive_paste_widget(key="dash_archive", min_blocks=2)
        return

    empty_state(
        "Без твоих текстов я буду угадывать. Вставь 3–8 своих постов — "
        "про чай, стол, тихое утро — и редакция станет настоящей 🤍"
    )
    archive_paste_widget(key="dash_archive", min_blocks=2)


def feedback_buttons(suggestion_id: int | None, key_prefix: str) -> None:
    if not suggestion_id:
        return
    fb_key = f"_fb_done_{key_prefix}_{suggestion_id}"
    already = st.session_state.get(fb_key)
    c1, c2, _ = st.columns([1.1, 1.4, 2.5])
    with c1:
        if st.button(
            "учту",
            key=f"{key_prefix}_yes_{suggestion_id}",
            help="Запомню этот выбор",
            type="secondary",
            disabled=already == "yes",
        ):
            try:
                api_post(f"/feedback/{suggestion_id}", json={"accepted": True, "note": ""})
                st.session_state[fb_key] = "yes"
                st.session_state["_toast"] = "Учтено 🤍"
                st.rerun()
            except Exception as exc:
                friendly_error(exc)
    with c2:
        if st.button(
            "не соглашусь",
            key=f"{key_prefix}_no_{suggestion_id}",
            help="Не моё, запомню",
            type="secondary",
            disabled=already == "no",
        ):
            try:
                api_post(f"/feedback/{suggestion_id}", json={"accepted": False, "note": ""})
                st.session_state[fb_key] = "no"
                st.session_state["_toast"] = "Запомнила — не моё"
                st.rerun()
            except Exception as exc:
                friendly_error(exc)
    if already:
        st.caption("учтено" if already == "yes" else "запомнила — не моё")


def _html(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "<br>")
    )


_SHADE_TITLES = {
    "recipes": "Рецепты",
    "beauty": "Бьюти",
    "home": "Дом",
    "vlogs": "Влоги",
}


def voice_status_widget() -> None:
    """Портрет голоса — как страница журнала, не анкета."""
    try:
        voice = api_get("/voice")
    except Exception as exc:
        friendly_error(exc)
        return
    if not voice:
        try:
            status = api_get("/onboarding/status")
            posts_n = int(status.get("posts_imported") or 0)
        except Exception as exc:
            friendly_error(exc)
            return
        if posts_n < 2:
            return
        st.caption("Голос ещё собирается из архива — первые советы могут быть без оттенка.")
        return

    profile = voice.get("profile") or {}
    tone = str(profile.get("tone") or "").strip()
    address = str(profile.get("address") or "").strip()
    shades = profile.get("shades") or {}
    phrases = [str(p).strip() for p in (profile.get("sample_phrases") or []) if str(p).strip()]
    lexicon = [str(w).strip() for w in (profile.get("lexicon") or []) if str(w).strip()]
    forbidden = [str(w).strip() for w in (profile.get("forbidden_vibes") or []) if str(w).strip()]

    bits: list[str] = ['<div class="tr-voice">']
    bits.append('<p class="tr-voice-kicker">Голос</p>')
    bits.append('<p class="tr-voice-title">Как ты звучишь</p>')
    if tone:
        bits.append(f'<p class="tr-voice-lead">{_html(tone)}</p>')
    if address:
        bits.append(
            '<p class="tr-voice-body">'
            '<span class="tr-voice-label">К кому</span>'
            f"{_html(address)}</p>"
        )
    shade_cards = []
    for key, title in _SHADE_TITLES.items():
        text = str(shades.get(key) or "").strip()
        if not text:
            continue
        shade_cards.append(
            f'<div class="tr-voice-shade"><div class="tr-voice-shade-t">{title}</div>'
            f"<p>{_html(text)}</p></div>"
        )
    if shade_cards:
        bits.append('<div class="tr-voice-grid">' + "".join(shade_cards) + "</div>")
    for quote in phrases[:4]:
        q = quote if quote.startswith("«") else f"«{quote}»"
        bits.append(f'<blockquote class="tr-voice-quote">{_html(q)}</blockquote>')
    if lexicon:
        bits.append(
            '<p class="tr-voice-words">'
            + " · ".join(_html(w) for w in lexicon[:8])
            + "</p>"
        )
    if forbidden:
        bits.append(
            '<p class="tr-voice-not">Рядом с тобой не звучит: '
            + "; ".join(_html(w) for w in forbidden[:4])
            + "</p>"
        )
    bits.append("</div>")
    st.markdown("".join(bits), unsafe_allow_html=True)
    with st.expander("добавить тексты в архив", expanded=False):
        archive_paste_widget(key="voice_more", min_blocks=1)


def empty_state(text: str, icon: str | None = None) -> None:
    mark = f'<span class="tr-empty-icon">{icon}</span>' if icon else ""
    st.markdown(f'<div class="tr-empty">{mark}{text}</div>', unsafe_allow_html=True)


def char_counter(text: str, *, warn_at: int = 600, hard_at: int = 1500) -> str:
    """Возвращает HTML для счётчика символов."""
    n = len(text or "")
    cls = "tr-counter"
    if n >= hard_at:
        cls = "tr-counter tr-counter--warn"
        suffix = f" · много ({hard_at}+)"
    elif n >= warn_at:
        cls = "tr-counter tr-counter--warn"
        suffix = " · подходим к пределу"
    else:
        suffix = ""
    return f'<div class="{cls}">{n} символов{suffix}</div>'


def copy_to_clipboard_button(text: str, *, key: str, label: str = "скопировать") -> None:
    """Кнопка «копировать» с JS-Clipboard API. Без external libs."""
    if not text:
        return
    safe = (
        text.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    st.markdown(
        f'''
        <button class="tr-copy-btn" id="{key}" type="button"
          onclick='navigator.clipboard.writeText(`{safe}`).then(function(){{var b=document.getElementById("{key}");b.classList.add("tr-copy-btn--done");b.innerHTML="✓ скопировано";setTimeout(function(){{b.classList.remove("tr-copy-btn--done");b.innerHTML="⧉ {label}";}},1800);}})'>
          ⧉ {label}
        </button>
        ''',
        unsafe_allow_html=True,
    )

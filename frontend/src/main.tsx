import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { restoreSession } from "./auth";
import "./styles.css";

// Сначала пытаемся молча восстановить вход по cookie обновления; пока идёт запрос, показывается «Проверяем вход…».
void restoreSession();

// Страница вернулась из «быстрой» истории браузера (кнопка «Назад» после выхода): состояние могло устареть,
// поэтому вход проверяется заново, и данные чужого завершённого сеанса не остаются на экране.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    void restoreSession();
  }
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

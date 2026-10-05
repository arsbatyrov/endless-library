import { type Msg, msg, raw } from "./i18n";

/**
 * Ошибка ответа API: хранит HTTP-код и (для ответа 422) ошибки по полям формы.
 * display это то, что показываем пользователю: либо текст сервера как есть (404, 409: поле detail, не переводится),
 * либо наше сообщение, которое переводится на язык интерфейса.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly display: Msg;
  /** Ключ: имя поля из запроса (например, "title"), значение: сообщение сервера. */
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, display: Msg, fieldErrors: Record<string, string> = {}) {
    super("text" in display ? display.text : display.key);
    this.status = status;
    this.display = display;
    this.fieldErrors = fieldErrors;
  }
}

/** Что показать, если не удалось ЗАГРУЗИТЬ данные: сообщение API или текст сетевой ошибки браузера. */
export function loadErrorMsg(error: unknown): Msg {
  if (error instanceof ApiError) {
    return error.display;
  }
  return error instanceof Error ? raw(error.message) : msg("common.unknownError");
}

/** Что показать, если не удалось ВЫПОЛНИТЬ действие (создать, удалить, выдать): сообщение API или «нет связи». */
export function actionErrorMsg(error: unknown): Msg {
  return error instanceof ApiError ? error.display : msg("common.networkError");
}

export async function toApiError(response: Response): Promise<ApiError> {
  let display: Msg = msg("api.requestFailed", { status: response.status });
  const fieldErrors: Record<string, string> = {};

  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      // 404, 409: одна причина строкой (текст сервера, показываем как есть)
      display = raw(body.detail);
    } else if (Array.isArray(body.detail)) {
      // 422: список проблем, у каждой loc = ["body", "<поле>"]
      display = msg("api.checkFields");
      for (const item of body.detail) {
        const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : undefined;
        if (typeof field === "string" && typeof item.msg === "string" && !(field in fieldErrors)) {
          fieldErrors[field] = item.msg;
        }
      }
    }
  } catch {
    // тело ответа не JSON: оставляем сообщение по умолчанию
  }

  return new ApiError(response.status, display, fieldErrors);
}

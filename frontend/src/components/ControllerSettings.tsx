import { useEffect, useState, type FormEvent } from "react";
import { ApiError, gdprApi, type GdprController } from "../api/client";
import { useTranslation } from "../i18n";

type Field = "name" | "tax_id" | "address" | "email" | "phone" | "dpo_contact";
const FIELDS: Field[] = ["name", "address", "tax_id", "email", "phone", "dpo_contact"];
const MAX: Record<Field, number> = { name: 200, tax_id: 32, address: 300, email: 200, phone: 40, dpo_contact: 200 };

type Form = Record<Field, string>;

function toForm(controller: GdprController): Form {
  return Object.fromEntries(FIELDS.map((field) => [field, controller[field] ?? ""])) as Form;
}

/**
 * Who the GDPR data controller is: put into the notice to buyers and the register of processing
 * activities (Help → GDPR). Only an administrator may save it, so only an administrator is shown it.
 */
export function ControllerSettings() {
  const { t } = useTranslation();
  const [form, setForm] = useState<Form | null>(null);
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    gdprApi
      .overview()
      .then((overview) => {
        if (!cancelled) setForm(toForm(overview.controller));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t("settings.controller.loadFailed"));
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!form) return;
    setState("saving");
    setError(null);
    try {
      // a field left empty is sent as nothing, which clears it
      const saved = await gdprApi.saveController(Object.fromEntries(FIELDS.map((field) => [field, form[field].trim() || null])));
      setForm(toForm(saved));
      setState("saved");
    } catch (err) {
      setState("idle");
      setError(err instanceof ApiError ? err.message : t("settings.controller.failed"));
    }
  };

  return (
    <section className="settings-section card tone-blue" aria-label={t("settings.controller.title")}>
      <h2>{t("settings.controller.title")}</h2>
      <p className="setting-row-help">{t("settings.controller.help")}</p>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      {form && (
        <form className="controller-form" onSubmit={save}>
          {FIELDS.map((field) => (
            <label key={field}>
              <span>{t(`gdpr.field.${field}`)}</span>
              <input
                type={field === "email" ? "email" : "text"}
                value={form[field]}
                maxLength={MAX[field]}
                onChange={(event) => {
                  setForm({ ...form, [field]: event.target.value });
                  setState("idle");
                }}
                aria-describedby={field === "dpo_contact" ? "controller-dpo-help" : undefined}
              />
            </label>
          ))}
          <p id="controller-dpo-help" className="setting-row-help">
            {t("settings.controller.dpoHelp")}
          </p>
          <div className="controller-actions">
            <button type="submit" disabled={state === "saving"}>
              {state === "saving" ? t("settings.controller.saving") : t("settings.controller.save")}
            </button>
            {state === "saved" && (
              <span role="status" className="controller-saved">
                {t("settings.controller.saved")}
              </span>
            )}
          </div>
        </form>
      )}
    </section>
  );
}

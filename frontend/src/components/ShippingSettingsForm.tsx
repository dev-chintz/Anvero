import { useEffect, useState, type FormEvent } from "react";
import { ApiError, shippingApi, type PackageSize, type ShippingSender } from "../api/client";
import { translate, useTranslation } from "../i18n";
import type { MessageKey } from "../i18n/messages";
import "../styles/Shipping.css";

const EMPTY_SENDER: ShippingSender = {
  name: "",
  company: null,
  street: "",
  postal_code: "",
  city: "",
  country_code: "PL",
  email: "",
  phone: "",
};
const EMPTY_PACKAGE: PackageSize = { length_cm: "", width_cm: "", height_cm: "", weight_kg: "" };

const SENDER_FIELDS: [keyof ShippingSender, MessageKey, string][] = [
  ["name", "shippingSettings.name", "text"],
  ["company", "shippingSettings.company", "text"],
  ["street", "shippingSettings.street", "text"],
  ["postal_code", "shippingSettings.postalCode", "text"],
  ["city", "shippingSettings.city", "text"],
  ["email", "shippingSettings.email", "email"],
  ["phone", "shippingSettings.phone", "tel"],
];
const PACKAGE_FIELDS: (keyof PackageSize)[] = ["length_cm", "width_cm", "height_cm", "weight_kg"];

/** The sender printed on labels, and the parcel size offered on each order. */
export function ShippingSettingsForm() {
  const { t } = useTranslation();
  const [sender, setSender] = useState<ShippingSender>(EMPTY_SENDER);
  const [pkg, setPkg] = useState<PackageSize>(EMPTY_PACKAGE);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<{ text: string; tone: "success" | "error" } | null>(null);

  useEffect(() => {
    shippingApi
      .settings()
      .then((stored) => {
        if (stored.sender) setSender(stored.sender);
        if (stored.default_package) setPkg(stored.default_package);
        setLoaded(true);
      })
      .catch(() => setNote({ text: translate("shippingSettings.loadFailed"), tone: "error" }));
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setNote(null);
    const hasPackage = PACKAGE_FIELDS.every((field) => Number(pkg[field]) > 0);
    try {
      await shippingApi.saveSettings({
        sender: { ...sender, company: sender.company?.trim() || null },
        default_package: hasPackage ? pkg : null,
      });
      setNote({ text: t("shippingSettings.saved"), tone: "success" });
    } catch (err) {
      setNote({
        text: err instanceof ApiError ? err.message : t("shippingSettings.saveFailed"),
        tone: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) {
    return note ? <p role="alert">{note.text}</p> : null;
  }

  return (
    <form className="shipping-settings" onSubmit={submit} aria-label={t("shippingSettings.title")}>
      <p className="subtitle">{t("shippingSettings.help")}</p>
      <fieldset>
        <legend>{t("shippingSettings.sender")}</legend>
        {SENDER_FIELDS.map(([field, label, type]) => (
          <label key={field}>
            {t(label)}
            <input
              type={type}
              value={sender[field] ?? ""}
              onChange={(e) => setSender({ ...sender, [field]: e.target.value })}
              required={field !== "company"}
              disabled={saving}
            />
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>{t("shippingSettings.package")}</legend>
        {PACKAGE_FIELDS.map((field) => (
          <label key={field}>
            {t(`label.field.${field}` as MessageKey)}
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step={field === "weight_kg" ? "0.001" : "0.1"}
              value={pkg[field]}
              onChange={(e) => setPkg({ ...pkg, [field]: e.target.value })}
              disabled={saving}
            />
          </label>
        ))}
      </fieldset>
      <button type="submit" disabled={saving}>
        {saving ? t("shippingSettings.saving") : t("shippingSettings.save")}
      </button>
      {note && (
        <p role={note.tone === "error" ? "alert" : "status"} className={`write-note write-${note.tone}`}>
          {note.text}
        </p>
      )}
    </form>
  );
}

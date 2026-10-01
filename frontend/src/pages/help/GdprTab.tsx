import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, gdprApi, type GdprOverview } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import {
  CONTROLLER_FIELDS,
  buyerNotice,
  missingControllerFields,
  noticeText,
  registerRows,
  securityFor,
  staffFor,
  type Block,
  type Controller,
} from "../../guide/gdpr";
import { useTranslation } from "../../i18n";

function NoticeBlocks({ blocks }: { blocks: Block[] }) {
  return (
    <div className="gdpr-notice-text" lang="pl">
      {blocks.map((block, index) => {
        if (block.kind === "title") return <h3 key={index}>{block.text}</h3>;
        if (block.kind === "heading") return <h4 key={index}>{block.text}</h4>;
        if (block.kind === "list") {
          return (
            <ul key={index}>
              {block.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          );
        }
        return <p key={index}>{block.text}</p>;
      })}
    </div>
  );
}

/** Who the controller is, and what is still missing from what the notice needs. */
function ControllerCard({ controller }: { controller: Controller }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const missing = missingControllerFields(controller);
  return (
    <section id="controller" className="card tone-blue gdpr-section" aria-labelledby="gdpr-controller-title">
      <h2 id="gdpr-controller-title">{t("gdpr.controller.title")}</h2>
      <p className="guide-intro">{t("gdpr.controller.lead")}</p>
      <dl className="gdpr-controller">
        {CONTROLLER_FIELDS.map((name) => (
          <div key={name} className="guide-part">
            <dt>{t(`gdpr.field.${name}`)}</dt>
            <dd>{controller[name] ?? <span className="order-muted">—</span>}</dd>
          </div>
        ))}
      </dl>
      {missing.length > 0 ? (
        <p role="alert" className="gdpr-missing">
          {t("gdpr.controller.missing", { fields: missing.map((name) => t(`gdpr.field.${name}`)).join(", ") })}{" "}
          {user?.role === "admin" ? (
            <Link to="/settings">{t("gdpr.controller.fill")} →</Link>
          ) : (
            t("gdpr.controller.askAdmin")
          )}
        </p>
      ) : (
        <p className="gdpr-complete">{t("gdpr.controller.complete")}</p>
      )}
    </section>
  );
}

function NoticeCard({ controller, orders, contacts }: { controller: Controller; orders: number; contacts: number }) {
  const { t } = useTranslation();
  const [copy, setCopy] = useState<"idle" | "done" | "failed">("idle");
  const blocks = buyerNotice(controller, { orders_years: orders, contacts_years: contacts });
  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(noticeText(blocks));
      setCopy("done");
    } catch {
      setCopy("failed");
    }
  };
  return (
    <section id="notice" className="card tone-teal gdpr-section" aria-labelledby="gdpr-notice-title">
      <div className="card-head">
        <h2 id="gdpr-notice-title">{t("gdpr.notice.title")}</h2>
        <button type="button" onClick={() => void copyText()}>
          {t("gdpr.notice.copy")}
        </button>
      </div>
      <p className="guide-intro">{t("gdpr.notice.lead")}</p>
      {copy === "done" && (
        <p role="status" className="gdpr-complete">
          {t("gdpr.notice.copied")}
        </p>
      )}
      {copy === "failed" && (
        <p role="alert" className="error-message">
          {t("gdpr.notice.copyFailed")}
        </p>
      )}
      <NoticeBlocks blocks={blocks} />
    </section>
  );
}

function RegisterCard({ controller, orders, contacts }: { controller: Controller; orders: number; contacts: number }) {
  const { t } = useTranslation();
  const rows = registerRows({ orders_years: orders, contacts_years: contacts });
  // the register is a Polish document whatever the interface's language
  const security = securityFor("pl");

  // only the register is printed, so the rest of the page and the menu stay off the paper
  const print = () => {
    const done = () => {
      document.body.classList.remove("printing-register");
      window.removeEventListener("afterprint", done);
    };
    document.body.classList.add("printing-register");
    window.addEventListener("afterprint", done);
    window.print();
  };

  return (
    <section id="register" className="card tone-green gdpr-section" aria-labelledby="gdpr-register-title">
      <div className="card-head">
        <h2 id="gdpr-register-title">{t("gdpr.register.title")}</h2>
        <button type="button" onClick={print}>
          {t("gdpr.register.print")}
        </button>
      </div>
      <p className="guide-intro">{t("gdpr.register.lead")}</p>
      <div id="gdpr-register" className="gdpr-register" lang="pl">
        <h3>Rejestr czynności przetwarzania danych osobowych (art. 30 ust. 1 RODO)</h3>
        <p>
          <strong>Administrator:</strong> {controller.name ?? "[uzupełnij: nazwa i forma prawna firmy]"},{" "}
          {controller.address ?? "[uzupełnij: adres siedziby]"}
          {controller.tax_id ? `, NIP ${controller.tax_id}` : ""}. <strong>Kontakt:</strong>{" "}
          {controller.email ?? "[uzupełnij: e-mail]"}
          {controller.phone ? `, tel. ${controller.phone}` : ""}.{" "}
          <strong>Inspektor ochrony danych:</strong> {controller.dpo_contact ?? "nie wyznaczono"}.
        </p>
        <div className="gdpr-table-wrap">
          <table className="gdpr-table">
            <thead>
              <tr>
                <th scope="col">Czynność przetwarzania</th>
                <th scope="col">Cel i podstawa prawna</th>
                <th scope="col">Kategorie osób</th>
                <th scope="col">Kategorie danych</th>
                <th scope="col">Odbiorcy</th>
                <th scope="col">Przekazanie poza EOG</th>
                <th scope="col">Termin usunięcia</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.activity}>
                  <th scope="row">{row.activity}</th>
                  <td>{row.purpose}</td>
                  <td>{row.subjects}</td>
                  <td>{row.data}</td>
                  <td>{row.recipients}</td>
                  <td>{row.transfers}</td>
                  <td>{row.retention}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h4>Ogólny opis środków bezpieczeństwa (art. 30 ust. 1 lit. g i art. 32 RODO)</h4>
        <ul>
          {security.map((measure) => (
            <li key={measure}>{measure}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/** What the law asks about personal data, and what a person on the team needs to know and do about it. */
export function GdprTab() {
  const { t, language } = useTranslation();
  const [overview, setOverview] = useState<GdprOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const staff = staffFor(language);

  useEffect(() => {
    let cancelled = false;
    gdprApi
      .overview()
      .then((next) => {
        if (!cancelled) setOverview(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t("gdpr.loadFailed"));
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  const sections = [
    ["controller", t("gdpr.controller.title")],
    ["notice", t("gdpr.notice.title")],
    ["data", t("gdpr.data.title")],
    ["recipients", t("gdpr.recipients.title")],
    ["requests", t("gdpr.requests.title")],
    ["breach", t("gdpr.breach.title")],
    ["security", t("gdpr.security.title")],
    ["register", t("gdpr.register.title")],
    ["checklist", t("gdpr.checklist.title")],
  ];

  return (
    <div className="gdpr">
      <p className="gdpr-disclaimer" role="note">
        {staff.disclaimer}
      </p>

      <nav className="gdpr-toc" aria-label={t("gdpr.contents")}>
        {sections.map(([id, label]) => (
          <a key={id} href={`#${id}`}>
            {label}
          </a>
        ))}
      </nav>

      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      {!overview && !error && <p role="status">{t("gdpr.loading")}</p>}

      {overview && (
        <>
          <ControllerCard controller={overview.controller} />
          <NoticeCard
            controller={overview.controller}
            orders={overview.retention.orders_years}
            contacts={overview.retention.contacts_years}
          />

          <section id="data" className="card tone-blue gdpr-section" aria-labelledby="gdpr-data-title">
            <h2 id="gdpr-data-title">{t("gdpr.data.title")}</h2>
            <p className="guide-intro">{staff.dataIntro}</p>
            <div className="gdpr-table-wrap">
              <table className="gdpr-table">
                <thead>
                  <tr>
                    <th scope="col">{staff.dataColumns.data}</th>
                    <th scope="col">{staff.dataColumns.where}</th>
                    <th scope="col">{staff.dataColumns.why}</th>
                    <th scope="col">{staff.dataColumns.kept}</th>
                  </tr>
                </thead>
                <tbody>
                  {staff.data.map((row) => (
                    <tr key={row.data}>
                      <td>{row.data}</td>
                      <td>{row.where}</td>
                      <td>{row.why}</td>
                      <td>{row.kept(overview.retention)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section id="recipients" className="card tone-blue gdpr-section" aria-labelledby="gdpr-recipients-title">
            <h2 id="gdpr-recipients-title">{t("gdpr.recipients.title")}</h2>
            <p className="guide-intro">{staff.recipientsIntro}</p>
            <dl className="guide-parts">
              {staff.recipients.map((recipient) => (
                <div key={recipient.name} className="guide-part">
                  <dt>{recipient.name}</dt>
                  <dd>{recipient.text}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section id="requests" className="card tone-amber gdpr-section" aria-labelledby="gdpr-requests-title">
            <h2 id="gdpr-requests-title">{t("gdpr.requests.title")}</h2>
            <p className="guide-intro">{staff.requestIntro}</p>
            <ol className="gdpr-steps">
              {staff.requests.map((step) => (
                <li key={step.title}>
                  <strong>{step.title}</strong>
                  <p>{step.text}</p>
                  {step.command && <pre className="gdpr-command">{step.command}</pre>}
                </li>
              ))}
            </ol>
            <p className="guide-note">{staff.requestNote}</p>
          </section>

          <section id="breach" className="card tone-red gdpr-section" aria-labelledby="gdpr-breach-title">
            <h2 id="gdpr-breach-title">{t("gdpr.breach.title")}</h2>
            <p className="guide-intro">{staff.breachIntro}</p>
            <ol className="gdpr-steps">
              {staff.breach.map((step) => (
                <li key={step.title}>
                  <strong>{step.title}</strong>
                  <p>{step.text}</p>
                  {step.command && <pre className="gdpr-command">{step.command}</pre>}
                </li>
              ))}
            </ol>
          </section>

          <section id="security" className="card tone-green gdpr-section" aria-labelledby="gdpr-security-title">
            <h2 id="gdpr-security-title">{t("gdpr.security.title")}</h2>
            <p className="guide-intro">{staff.securityIntro}</p>
            <ul className="guide-list">
              {securityFor(language).map((measure) => (
                <li key={measure}>{measure}</li>
              ))}
            </ul>
          </section>

          <RegisterCard
            controller={overview.controller}
            orders={overview.retention.orders_years}
            contacts={overview.retention.contacts_years}
          />

          <section id="checklist" className="card tone-amber gdpr-section" aria-labelledby="gdpr-checklist-title">
            <h2 id="gdpr-checklist-title">{t("gdpr.checklist.title")}</h2>
            <p className="guide-intro">{staff.checklistIntro}</p>
            <dl className="guide-parts">
              {staff.checklist.map((item) => (
                <div key={item.title} className="guide-part">
                  <dt>{item.title}</dt>
                  <dd>{item.text}</dd>
                </div>
              ))}
            </dl>
          </section>
        </>
      )}
    </div>
  );
}

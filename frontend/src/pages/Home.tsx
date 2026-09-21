import { Link } from "react-router-dom";
import { useTranslation } from "../i18n";

export function Home() {
  const { t } = useTranslation();
  return (
    <section className="home">
      <h1>Anvero</h1>
      <p>{t("home.tagline")}</p>
      <Link to="/orders" className="button-link">
        {t("home.viewOrders")}
      </Link>
    </section>
  );
}

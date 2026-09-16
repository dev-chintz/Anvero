import { Link } from "react-router-dom";

export function Home() {
  return (
    <section className="home">
      <h1>Anvero</h1>
      <p>Marketplace sales management platform.</p>
      <Link to="/orders" className="button-link">
        View Orders
      </Link>
    </section>
  );
}

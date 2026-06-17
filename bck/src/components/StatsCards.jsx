export default function StatsCards({ items }) {

  const total = items.length;

  const promedio =
    total > 0
      ? Math.round(
          items.reduce(
            (acc, item) => acc + (item.score || 0),
            0
          ) / total
        )
      : 0;

  const topScore =
    total > 0
      ? Math.max(...items.map(i => i.score || 0))
      : 0;

  return (
    <div className="stats">

      <div className="card">
        <h3>Total Remates</h3>
        <p>{total}</p>
      </div>

      <div className="card">
        <h3>Promedio Score</h3>
        <p>{promedio}</p>
      </div>

      <div className="card">
        <h3>Mejor Score</h3>
        <p>{topScore}</p>
      </div>

    </div>
  );
}
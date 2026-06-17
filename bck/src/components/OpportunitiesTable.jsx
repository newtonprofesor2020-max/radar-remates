export default function OpportunitiesTable({
  items
}) {

  return (
    <table>

      <thead>
        <tr>
          <th>Distrito</th>
          <th>Base</th>
          <th>Tasación</th>
          <th>Score</th>
        </tr>
      </thead>

      <tbody>

        {items.map(item => (

          <tr key={item.id}>
            <td>{item.distrito}</td>
            <td>S/ {item.precio_base}</td>
            <td>S/ {item.tasacion}</td>
            <td>{item.score}</td>
          </tr>

        ))}

      </tbody>

    </table>
  );
}
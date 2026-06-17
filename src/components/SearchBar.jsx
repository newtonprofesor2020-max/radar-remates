export default function SearchBar({
  search,
  setSearch
}) {

  return (
    <input
      type="text"
      placeholder="Buscar distrito..."
      value={search}
      onChange={(e) =>
        setSearch(e.target.value)
      }
    />
  );
}
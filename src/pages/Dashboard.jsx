import { useEffect, useState } from "react";

import { api } from "../api/api";

import StatsCards from "../components/StatsCards";
import SearchBar from "../components/SearchBar";
import OpportunitiesTable from "../components/OpportunitiesTable";

export default function Dashboard() {

  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");

  useEffect(() => {

    api.get("/ranking")
      .then(res => {
        setItems(res.data);
      });

  }, []);

  const filtered = items.filter(item =>
    item.distrito
      ?.toLowerCase()
      .includes(search.toLowerCase())
  );

  return (
    <div className="container">

      <h1>Radar de Remates</h1>

      <StatsCards items={items} />

      <SearchBar
        search={search}
        setSearch={setSearch}
      />

      <OpportunitiesTable
        items={filtered}
      />

    </div>
  );
}
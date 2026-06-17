import { Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard.jsx";
import DetalleInmueble from "./pages/DetalleInmueble.jsx";
import Favoritos from "./pages/Favoritos.jsx";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/inmueble/:id" element={<DetalleInmueble />} />
      <Route path="/favoritos" element={<Favoritos />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;

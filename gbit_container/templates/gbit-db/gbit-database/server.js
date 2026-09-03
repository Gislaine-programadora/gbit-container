// gbit-database — servidor de backend autocontido.
// O motor gbit-db-dados é integrado diretamente neste serviço
// (instalado via npm e executado junto com o server).
const express = require("express");

const app = express();
const PORT = process.env.PORT || 4200;

app.use(express.json());

app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "gbit-database" });
});

app.get("/", (req, res) => {
  res.json({ message: "gbit-database rodando", port: PORT });
});

// Rotas de API do motor gbit-db-dados serão registradas abaixo
// quando o módulo estiver disponível (instalado no entrypoint).
try {
  const motor = require("gbit-db-dados");
  if (typeof motor === "function") {
    app.use("/api", motor());
  } else if (typeof motor === "object" && typeof motor.router === "function") {
    app.use("/api", motor.router());
  } else if (typeof motor === "object" && motor.router) {
    app.use("/api", motor.router);
  }
  console.log("Motor gbit-db-dados integrado com sucesso.");
} catch (e) {
  console.warn("Motor gbit-db-dados nao encontrado ainda — rodando em modo standalone.");
  console.warn("Se o motor foi instalado no entrypoint, reinicie o container.");
}

app.listen(PORT, () => {
  console.log(`gbit-database ouvindo na porta ${PORT}`);
});
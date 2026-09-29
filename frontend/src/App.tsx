import "./App.css";

/**
 * Écran de fondation (Étape 2). Aucune fonctionnalité de transcription
 * audio n'est encore branchée ici — voir docs/ARCHITECTURE.md pour le
 * pipeline prévu.
 */
function App() {
  return (
    <main className="app">
      <h1>GuitarRiff</h1>
      <p>
        Transformez un lien YouTube ou un fichier audio en tablatures,
        partitions et pistes musicales éditables.
      </p>
      <p className="status">
        Fondations du projet en place — la transcription audio n'est pas
        encore implémentée.
      </p>
    </main>
  );
}

export default App;

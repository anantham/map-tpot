import './App.css'
import GraphExplorer from './GraphExplorer'

function App() {
  return (
    <div style={{ height: '100vh' }}>
      <GraphExplorer dataUrl="/analysis_output.json" />
    </div>
  )
}

export default App

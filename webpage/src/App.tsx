// import { useState } from 'react'
import TextBox from './components/textbox.tsx'
import './App.css'

function App() {
  return (
    <>
      <h1>Instagram Post Dowloader</h1>
      <p>Paste the share link of any public Instagram post.</p>
      <div className="flex items-center justify-center"><TextBox /></div>
    </>
  )
}

export default App

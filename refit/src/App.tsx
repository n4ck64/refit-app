import { useState, useEffect } from 'react'
import Chat from './pages/Chat'
import Exercises from './pages/Exercises'
import Plans from './pages/Plans'

type User = { user_id: number, full_name: string }

const AVATARS: Record<number, string> = {
  1: "Sam.png",
  2: "Leo.png",
  3: "Rita.png",
  4: "David.png",
  5: "Marcus.png",
  6: "Suping.png",
}

function App() {
  const [activeTab, setActiveTab] = useState("chat")
  const [planNonce, setPlanNonce] = useState(0)

  // dev-only user switcher 
  const [users, setUsers] = useState<User[]>([])
  const [userId, setUserId] = useState(1)

  useEffect(() => {
    fetch("http://localhost:8000/users")
      .then(res => res.json())
      .then(setUsers)
  }, [])

  // handed to Chat so its "Plans" link can jump here AND force a fresh load.
  const goToPlans = () => {
    setPlanNonce(n => n + 1)
    setActiveTab("plans")
  }


  return (
    <>
      <h1>ReFit</h1>
      <div id="layout">
        <div id="sidebar">
          <div className="sidebar-tab" onClick={() => setActiveTab("chat")}>Chat</div>
          <div className="sidebar-tab" onClick={() => setActiveTab("exercises")}>Exercises</div>
          <div className="sidebar-tab" onClick={() => setActiveTab("plans")}>Plans</div>
          <select value={userId} onChange={e => setUserId(Number(e.target.value))}
            title="Switch test user (dev only)"
            style={{ marginTop: "20px", width: "80%", marginLeft: "20px" }}>
            {users.map(u => (
              <option key={u.user_id} value={u.user_id}>{u.full_name}</option>
            ))}
          </select>
          <img id="user-avatar" src={`/${AVATARS[userId] ?? "chad.png"}`} />
        </div>

        <div style={{ display: activeTab === "chat" ? "contents" : "none" }}>
          <Chat goToPlans={goToPlans} userId={userId} />
        </div>
        <div style={{ display: activeTab === "exercises" ? "contents" : "none" }}>
          <Exercises />
        </div>
        <div style={{ display: activeTab === "plans" ? "contents" : "none" }}>
          <Plans refreshSignal={planNonce} userId={userId} />
        </div>
      </div>
    </>

  )
}

export default App


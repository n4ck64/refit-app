import { useState, useEffect } from 'react'

// The shape of one exercise in the plan JSON from GET /plan.
type PlanExercise = { name: string; day: string; sets: number; reps: number }
type Plan = { exercises: PlanExercise[] }

// What we track per row as the user works out: done?, the ACTUAL sets/reps hit,
// and the working weight (weight is user-entered — the plan can't know your strength).
type Progress = { done: boolean; sets: number; reps: number; weight: number }

const WEEK = ["monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday"]
const WEEK_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const MONTHS = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"]

// shared style for the small number inputs (actual sets / reps / weight)
const numInput = {
    width: "42px", padding: "4px 6px", borderRadius: "6px",
    border: "none", background: "rgb(255,255,232)", fontSize: "13px",
    textAlign: "center" as const,
}

// key an exercise by day + name, so progress["monday-Squat"] is that one row
const rowKey = (e: PlanExercise) => `${e.day}-${e.name}`


// ── one editable exercise row (shared by the weekly list and the calendar's day panel)
function ExerciseRow({ e, p, onChange }: {
    e: PlanExercise
    p: Progress
    onChange: (patch: Partial<Progress>) => void   // caller already knows which row
}) {
    return (
        <div style={{
            display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap",
            background: "rgb(255,255,206)", borderRadius: "10px",
            padding: "8px 12px", marginBottom: "6px",
            opacity: p.done ? 0.55 : 1,
        }}>
            <input type="checkbox" checked={p.done}
                onChange={() => onChange({ done: !p.done })} />

            <span style={{
                flex: 1, minWidth: "120px", fontWeight: 500,
                textDecoration: p.done ? "line-through" : "none",
            }}>{e.name}</span>

            <span style={{ fontSize: "12px", color: "grey" }}>target {e.sets}×{e.reps}</span>

            {/* actual sets × reps @ weight — all editable */}
            <input type="number" min={0} style={numInput} value={p.sets}
                onChange={ev => onChange({ sets: Number(ev.target.value) })} />
            <span style={{ color: "grey" }}>×</span>
            <input type="number" min={0} style={numInput} value={p.reps}
                onChange={ev => onChange({ reps: Number(ev.target.value) })} />
            <span style={{ color: "grey" }}>@</span>
            <input type="number" min={0} style={numInput} value={p.weight}
                onChange={ev => onChange({ weight: Number(ev.target.value) })} />
            <span style={{ color: "grey", fontSize: "12px" }}>kg</span>
        </div>
    )
}


// ── the month calendar: real dates, training days highlighted, click one to see it
function MonthlyView({ plan, progress, onChange }: {
    plan: Plan
    progress: Record<string, Progress>
    onChange: (key: string, patch: Partial<Progress>) => void
}) {
    const [selected, setSelected] = useState<Date | null>(null)

    const today = new Date()
    const year = today.getFullYear()
    const month = today.getMonth()   // 0 = January

    // which weekday NAMES are training days (i.e. the plan has exercises on them)
    const trainingDays = new Set(plan.exercises.map(e => e.day))

    // JS Date.getDay() is 0=Sun..6=Sat, but our WEEK starts Monday. This shifts it
    // so Monday=0 ... Sunday=6, matching WEEK, so we can look the day name up.
    const weekdayName = (d: Date) => WEEK[(d.getDay() + 6) % 7]

    // build the grid of cells: leading blanks, then each date, padded to full weeks
    const daysInMonth = new Date(year, month + 1, 0).getDate()      // 0th of next month = last of this
    const firstOffset = (new Date(year, month, 1).getDay() + 6) % 7 // blanks before the 1st (Mon-first)
    const cells: (Date | null)[] = []
    for (let i = 0; i < firstOffset; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d))
    while (cells.length % 7 !== 0) cells.push(null)                 // trailing blanks

    // exercises to show when a training day is selected
    const dayExercises = selected
        ? plan.exercises.filter(e => e.day === weekdayName(selected))
        : []

    return (
        <div>
            <h3 style={{ margin: "0 0 12px" }}>{MONTHS[month]} {year}</h3>

            {/* weekday header row */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: "6px", marginBottom: "6px" }}>
                {WEEK_SHORT.map(d => (
                    <div key={d} style={{ textAlign: "center", fontSize: "12px", color: "grey" }}>{d}</div>
                ))}
            </div>

            {/* date cells */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: "6px" }}>
                {cells.map((date, i) => {
                    if (!date) return <div key={i} />   // blank pad cell
                    const isTraining = trainingDays.has(weekdayName(date))
                    const isSelected = selected?.getDate() === date.getDate()
                    const isToday = date.getDate() === today.getDate()
                    return (
                        <div key={i}
                            onClick={() => isTraining && setSelected(date)}
                            style={{
                                aspectRatio: "1", display: "flex",
                                alignItems: "center", justifyContent: "center",
                                borderRadius: "8px", fontSize: "14px",
                                // training days pop in yellow and are clickable; rest days greyed
                                background: isTraining ? "rgb(255,255,206)" : "transparent",
                                color: isTraining ? "#000" : "#bbb",
                                cursor: isTraining ? "pointer" : "default",
                                fontWeight: isToday ? 700 : 400,
                                outline: isSelected ? "2px solid #c9a227" : "none",
                            }}>
                            {date.getDate()}
                        </div>
                    )
                })}
            </div>

            {/* the selected day's exercises, using the same editable row as weekly */}
            {selected && (
                <div style={{ marginTop: "16px" }}>
                    <h4 style={{ textTransform: "capitalize", margin: "0 0 8px" }}>
                        {weekdayName(selected)} {selected.getDate()}
                    </h4>
                    {dayExercises.map(e => {
                        const key = rowKey(e)
                        const p = progress[key] ?? { done: false, sets: e.sets, reps: e.reps, weight: 0 }
                        return <ExerciseRow key={key} e={e} p={p}
                            onChange={patch => onChange(key, patch)} />
                    })}
                </div>
            )}
        </div>
    )
}


function Plans({ refreshSignal, userId }: { refreshSignal: number, userId: number }) {
    const [plan, setPlan] = useState<Plan | null>(null)
    const [progress, setProgress] = useState<Record<string, Progress>>({})
    const [view, setView] = useState<"weekly" | "monthly">("weekly")

    // fetch the plan on mount, whenever refreshSignal changes (App bumps it when
    // a new plan is built or edited), AND whenever the active user changes, then
    // seed a progress entry for every exercise
    useEffect(() => {
        async function load() {
            const res = await fetch(`http://localhost:8000/plan?user_id=${userId}`)
            const data = await res.json()
            setPlan(data)
            if (data) {
                const seed: Record<string, Progress> = {}
                for (const e of data.exercises) {
                    seed[rowKey(e)] = { done: false, sets: e.sets, reps: e.reps, weight: 0 }
                }
                setProgress(seed)
            }
        }
        load()
    }, [refreshSignal, userId])

    // update ONE row immutably 
    function onChange(key: string, patch: Partial<Progress>) {
        setProgress(prev => ({ ...prev, [key]: { ...prev[key], ...patch } }))
    }

    if (!plan) {
        return (
            <div id="chat-window">
                <h2>Plans</h2>
                <p style={{ color: "grey" }}>No plan yet — ask for one in Chat.</p>
            </div>
        )
    }

    return (
        <div id="chat-window">
            {/* view toggle */}
            <div style={{ marginBottom: "12px", display: "flex", gap: "8px" }}>
                <button className="choice-btn"
                    style={{ fontWeight: view === "weekly" ? 600 : 400 }}
                    onClick={() => setView("weekly")}>Weekly</button>
                <button className="choice-btn"
                    style={{ fontWeight: view === "monthly" ? 600 : 400 }}
                    onClick={() => setView("monthly")}>Monthly</button>
            </div>

            {view === "weekly" && WEEK.map(day => {
                const dayExercises = plan.exercises.filter(e => e.day === day)
                const isRest = dayExercises.length === 0
                return (
                    <div key={day} style={{ marginBottom: "16px", opacity: isRest ? 0.45 : 1 }}>
                        <h3 style={{ textTransform: "capitalize", margin: "0 0 8px" }}>{day}</h3>
                        {isRest
                            ? <div style={{ color: "grey", fontStyle: "italic" }}>Rest day</div>
                            : dayExercises.map(e => {
                                const key = rowKey(e)
                                const p = progress[key] ?? { done: false, sets: e.sets, reps: e.reps, weight: 0 }
                                return <ExerciseRow key={key} e={e} p={p}
                                    onChange={patch => onChange(key, patch)} />
                            })}
                    </div>
                )
            })}

            {view === "monthly" && (
                <MonthlyView plan={plan} progress={progress} onChange={onChange} />
            )}
        </div>
    )
}

export default Plans

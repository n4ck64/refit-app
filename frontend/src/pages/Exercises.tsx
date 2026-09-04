import { useState, useEffect } from 'react'
import ExerciseDetail, { DIFFICULTY_COLORS, NEUTRAL, pill, type Exercise } from '../components/ExerciseDetail'


function Exercises() {

    const [exercises, setExercises] = useState<Exercise[]>([])

    const FILTER_FIELDS = ["difficulty", "equipment", "type"] as const

    const [filters, setFilters] = useState<Record<string, string | null>>({})
    const [showFilters, setShowFilters] = useState(false)
    const [search, setSearch] = useState("")
    const [selected, setSelected] = useState<{ ex: Exercise; rect: DOMRect } | null>(null)

    function toggleFilter(field: string, value: string) {
        setFilters(prev => ({
            ...prev,
            [field]: prev[field] === value ? null : value
        }))
    }

    useEffect(() => {
        async function load() {
            const res = await fetch("http://localhost:8000/exercises")
            const data = await res.json()
            setExercises(data)
        }
        load()
    }, []) // run once, right after component first mounts, that's what the empty square brackets mean there

    const primaryMuscles = [...new Set(
        exercises.flatMap(ex => ex.muscles.Primary.split(", "))
    )].filter(m => m !== "none listed").sort()

    const visible = exercises.filter(ex => {
        const flatOk = FILTER_FIELDS.every(field => {
            const active = filters[field]
            return !active || ex[field] === active
        })
        const muscle = filters.primaryMuscle
        const muscleOk = !muscle || ex.muscles.Primary.split(", ").includes(muscle)
        const searchOk = ex.name.toLowerCase().includes(search.toLowerCase())
        return flatOk && muscleOk && searchOk
    })

    const activeCount = Object.values(filters).filter(Boolean).length

    // keep the detail popup fully on screen: clamp its position to the viewport
    const margin = 12
    const panelWidth = selected ? Math.max(selected.rect.width, 320) : 0
    const panelLeft = selected ? Math.max(margin, Math.min(selected.rect.left, window.innerWidth - panelWidth - margin)) : 0
    const panelTop = selected ? Math.min(selected.rect.top, window.innerHeight - 160) : 0
    const panelMaxHeight = window.innerHeight - panelTop - margin


    return (
        <div id="chat-window">
            <div style={{ marginBottom: "12px" }}>
                <button className="choice-btn" onClick={() => setShowFilters(true)}>
                    Filters{activeCount > 0 ? ` (${activeCount})` : ""}
                </button>
                <input
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="Search exercises..."
                    style={{ flex: 1, padding: "8px 12px", borderRadius: "8px", border: "none", background: "rgb(255,255,206)", fontSize: "14px" }}
                />
            </div>

            {showFilters && (
                <div
                    onClick={() => setShowFilters(false)}
                    style={{
                        position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)",
                        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100
                    }}
                >
                    <div
                        onClick={e => e.stopPropagation()}
                        style={{
                            background: "rgb(255,255,232)", borderRadius: "16px", padding: "20px",
                            width: "min(90vw, 480px)", maxHeight: "80vh", overflowY: "auto",
                            boxShadow: "0 4px 20px rgba(0,0,0,0.2)"
                        }}
                    >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                            <h3 style={{ margin: 0 }}>Filters</h3>
                            <button className="choice-btn" onClick={() => setFilters({})}>Clear all</button>
                        </div>

                        {FILTER_FIELDS.map(field => (
                            <div key={field} style={{ marginBottom: "12px" }}>
                                <div style={{ fontSize: "12px", color: "grey", marginBottom: "6px", textTransform: "capitalize" }}>{field}</div>
                                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                                    {[...new Set(exercises.map(ex => ex[field]))].sort().map(value => (
                                        <button
                                            key={value}
                                            className="choice-btn"
                                            style={{ fontWeight: filters[field] === value ? 500 : 400 }}
                                            onClick={() => toggleFilter(field, value)}
                                        >
                                            {value}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        ))}

                        <div style={{ marginBottom: "16px" }}>
                            <div style={{ fontSize: "12px", color: "grey", marginBottom: "6px" }}>Primary muscle</div>
                            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                                {primaryMuscles.map(muscle => (
                                    <button
                                        key={muscle}
                                        className="choice-btn"
                                        style={{ fontWeight: filters.primaryMuscle === muscle ? 500 : 400 }}
                                        onClick={() => toggleFilter("primaryMuscle", muscle)}
                                    >
                                        {muscle}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <button className="choice-btn" onClick={() => setShowFilters(false)}>Done</button>
                    </div>
                </div>
            )}

            {selected && (
                <div
                    onClick={() => setSelected(null)}
                    style={{
                        position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 100
                    }}
                >
                    <div
                        onClick={e => e.stopPropagation()}
                        style={{
                            position: "fixed",
                            top: panelTop,
                            left: panelLeft,
                            width: panelWidth,
                            background: "rgb(255,255,232)", borderRadius: "16px", padding: "20px",
                            maxHeight: panelMaxHeight, overflowY: "auto",
                            boxShadow: "0 4px 20px rgba(0,0,0,0.2)"
                        }}
                    >
                        <ExerciseDetail ex={selected.ex} onClose={() => setSelected(null)} />
                    </div>
                </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px" }}>
                {visible.map(ex => (
                    <div key={ex.id}
                        onClick={(e) => setSelected({ ex, rect: e.currentTarget.getBoundingClientRect() })}
                        style={{
                            background: "rgb(255,255,206)",
                            borderRadius: "12px",
                            padding: "12px",
                            display: "flex",
                            flexDirection: "column",
                            gap: "8px",
                            boxShadow: "0 2px 4px rgba(0,0,0,0.08)",
                            cursor: "pointer",
                        }}
                    >
                        <div style={{ fontWeight: 500, fontSize: "20px" }}>{ex.name}</div>

                        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                            <span style={pill(DIFFICULTY_COLORS[ex.difficulty] || NEUTRAL)}>{ex.difficulty}</span>
                            <span style={pill(NEUTRAL)}>{ex.type}</span>
                            <span style={pill(NEUTRAL)}>{ex.equipment}</span>
                        </div>
                        <div style={{ fontSize: "12px", color: "#5a4a1a" }}>
                            <span style={{ color: "grey" }}>Primary: </span>{ex.muscles.Primary}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}

export default Exercises

import MuscleMap from './MuscleMap'

export type Exercise = {
    id: number
    name: string
    description: string
    type: string
    difficulty: string
    equipment: string
    muscles: {
        Primary: string
        Secondary: string
        Stabiliser: string
    }
    muscle_ids: {
        Primary: number[]
        Secondary: number[]
        Stabiliser: number[]
    }
}

export const DIFFICULTY_COLORS: Record<string, { bg: string; text: string }> = {
    Easy: { bg: "#eaf3de", text: "#3b6d11" },   // green
    Medium: { bg: "#faeeda", text: "#854f0b" },   // amber
    Hard: { bg: "#fcebeb", text: "#a32d2d" },   // red
}
export const NEUTRAL = { bg: "#f1efe8", text: "#444441" } // grey, for type + equipment

export function pill(colors: { bg: string; text: string }) {
    return {
        fontSize: "11px",
        padding: "2px 8px",
        borderRadius: "20px",
        background: colors.bg,
        color: colors.text,
    }
}

// The exercise-detail card content: name, pills, muscle roles, the muscle map, and descriptions

function ExerciseDetail({ ex, onClose }: { ex: Exercise; onClose: () => void }) {
    return (
        <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <h3 style={{ margin: 0 }}>{ex.name}</h3>
                <button className="choice-btn" onClick={onClose}>Close</button>
            </div>

            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "16px" }}>
                <span style={pill(DIFFICULTY_COLORS[ex.difficulty] || NEUTRAL)}>{ex.difficulty}</span>
                <span style={pill(NEUTRAL)}>{ex.type}</span>
                <span style={pill(NEUTRAL)}>{ex.equipment}</span>
            </div>

            <div style={{ fontSize: "13px", color: "grey", marginBottom: "16px" }}>
                <div>Primary: {ex.muscles.Primary}</div>
                <div>Secondary: {ex.muscles.Secondary}</div>
                <div>Stabiliser: {ex.muscles.Stabiliser}</div>
            </div>

            <div style={{ borderTop: "1px solid rgba(0,0,0,0.08)", paddingTop: "14px", marginBottom: "16px" }}>
                <MuscleMap key={ex.id} muscleIds={ex.muscle_ids} />
            </div>

            <div style={{ fontSize: "14px", lineHeight: 1.5 }}>{ex.description}</div>
        </div>
    )
}

export default ExerciseDetail

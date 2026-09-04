import { useEffect, useRef, useState } from 'react'

export type MuscleIds = { Primary: number[]; Secondary: number[]; Stabiliser: number[] }

// bones use the colour below and are left alone
const BONE_COLORS = ["#e5ecef", "#dbd5c7", "#fde8cc"]

const ROLE_COLOR: Record<keyof MuscleIds, string> = {
    Primary: "#d85a30",
    Secondary: "#ffbc41",
    Stabiliser: "#b9c9a8",
}
const BASE_FILL = "#d9d6c8"

// the SVG is ~330KB — fetch it once and reuse the text across every popup open

let cachedSvgText: string | null = null
let fetchPromise: Promise<string> | null = null

function loadSvg(): Promise<string> {
    if (cachedSvgText) return Promise.resolve(cachedSvgText)
    if (!fetchPromise) {
        fetchPromise = fetch("/muscle_map.svg").then(res => res.text()).then(text => {
            cachedSvgText = text
            return text
        })
    }
    return fetchPromise
}

// Renders the front+back muscle diagram, tinted by role for one exercise.

function MuscleMap({ muscleIds }: { muscleIds: MuscleIds }) {
    const containerRef = useRef<HTMLDivElement>(null)
    const [loaded, setLoaded] = useState(false)

    useEffect(() => {
        let cancelled = false
        loadSvg().then(svgText => {
            if (cancelled || !containerRef.current) return
            containerRef.current.innerHTML = svgText
            setLoaded(true)
        })
        return () => { cancelled = true }
    }, [])

    useEffect(() => {
        if (!loaded || !containerRef.current) return
        const svg = containerRef.current.querySelector("svg")
        if (!svg) return

        // grey every muscle path — labelled or not 
        svg.querySelectorAll<SVGPathElement>("path").forEach(el => {
            const style = el.getAttribute("style") || ""
            if (!/fill\s*:/.test(style)) return
            if (/fill:\s*none/.test(style)) return
            if (BONE_COLORS.some(c => style.includes(c))) return
            el.style.fill = BASE_FILL
        })
            ; (Object.keys(muscleIds) as (keyof MuscleIds)[]).forEach(role => {
                muscleIds[role].forEach(id => {
                    svg.querySelectorAll<SVGElement>(`.m${id}`).forEach(el => {
                        el.style.fill = ROLE_COLOR[role]
                    })
                })
            })
    }, [loaded, muscleIds])

    const noneHighlighted =
        muscleIds.Primary.length === 0 &&
        muscleIds.Secondary.length === 0 &&
        muscleIds.Stabiliser.length === 0

    if (noneHighlighted) return null

    return (
        <div>
            <div ref={containerRef} style={{ width: "100%", maxWidth: "380px", margin: "0 auto" }} />
            {loaded && (
                <div style={{ display: "flex", justifyContent: "center", gap: "14px", marginTop: "12px" }}>
                    <LegendItem color={ROLE_COLOR.Primary} label="primary" />
                    <LegendItem color={ROLE_COLOR.Secondary} label="secondary" />
                    <LegendItem color={ROLE_COLOR.Stabiliser} label="stabiliser" />
                </div>
            )}
        </div>
    )
}

function LegendItem({ color, label }: { color: string; label: string }) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "grey" }}>
            <span style={{ width: "9px", height: "9px", borderRadius: "2px", background: color, display: "inline-block" }} />
            {label}
        </div>
    )
}

export default MuscleMap

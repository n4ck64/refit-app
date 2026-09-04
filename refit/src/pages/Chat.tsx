import { useState, useEffect, useRef, type ChangeEvent, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import ExerciseDetail, { type Exercise } from '../components/ExerciseDetail'


type Message = {
    role: "user" | "bot"
    content: string
    pulsing?: boolean // ? means optional
    mediaUrl?: string
    mediaType?: "image" | "video"
    // exercise names the backend grounded THIS reply on (see the EXERCISES:
    // sentinel token below) — tappable in the rendered text, opening the same
    // ExerciseDetail/MuscleMap the Exercises tab uses
    linkableExercises?: string[]
}

// wraps any occurrence of a known exercise name inside text children with a
// tappable span — mirrors the existing #plans/#nutrition link-interception
// idea, but for plain prose rather than markdown links, since the model names
// exercises in running text, not as [links](to them)
function linkify(children: ReactNode, names: string[] | undefined, onPick: (name: string) => void): ReactNode {
    if (!names || names.length === 0) return children
    // longest name first, so "Barbell Bench Press" wins over a bare "Bench Press"
    const sorted = [...names].sort((a, b) => b.length - a.length)
    const pattern = new RegExp(`(${sorted.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi")

    function linkifyString(text: string, key: string): ReactNode[] {
        const parts = text.split(pattern)
        return parts.map((part, i) => {
            const match = sorted.find(n => n.toLowerCase() === part.toLowerCase())
            return match
                ? <a key={`${key}-${i}`} href="#exercise" onClick={e => { e.preventDefault(); onPick(match) }}>{part}</a>
                : part
        })
    }

    const arr = Array.isArray(children) ? children : [children]
    return arr.flatMap((child, i) =>
        typeof child === "string" ? linkifyString(child, String(i)) : child
    )
}

type Choices = {
    message: string
    names: string[]
} | null

function Chat({ goToPlans, userId }: {
    goToPlans: () => void, userId: number
}) {
    const [pendingImage, setPendingImage] = useState<string | null>(null)
    const [pendingVideoChoice, setPendingVideoChoice] = useState<string | null>(null)
    const [pendingFileType, setPendingFileType] = useState<"image" | "video" | null>(null)
    const [manualVideoEntry, setManualVideoEntry] = useState(false)
    const [messages, setMessages] = useState<Message[]>([])
    const [choices, setChoices] = useState<Choices>(null)
    const [message, setMessage] = useState<string>("")
    const bottomRef = useRef<HTMLDivElement>(null)
    const [previewUrl, setPreviewUrl] = useState<string | null>(null)
    const [exercises, setExercises] = useState<Exercise[]>([])
    const [openedExercise, setOpenedExercise] = useState<Exercise | null>(null)

    useEffect(() => {
        async function load() {
            const res = await fetch("http://localhost:8000/exercises")
            setExercises(await res.json())
        }
        load()
    }, [])

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])   // runs every time messages changes

    // switching the dev user resets backend conversational state (see
    // run_chat_pipeline), so clear the visible transcript to match — otherwise
    // the previous persona's messages linger over a backend that's forgotten them
    useEffect(() => {
        setMessages([])
        setChoices(null)
    }, [userId])

    const STATUS_TOKENS = new Set([
        "Commencing...", "Classifying User Query...", "Thinking...", "Reviewing...", "Analysing...", "Processing...", "Hungry...", "Uploading...", "Making Plan..."
    ])


    function updateLastBot(content: string, pulsing: boolean) {
        setMessages(prev => {
            const copy = [...prev]
            copy[copy.length - 1] = { role: "bot", content, pulsing }
            return copy
        })
    }

    // patches linkableExercises onto the last message without touching its
    // content — the EXERCISES: token always arrives after the real text, once
    // per turn, so there's nothing else left to preserve
    function updateLastBotExercises(names: string[]) {
        setMessages(prev => {
            const copy = [...prev]
            const last = copy[copy.length - 1]
            copy[copy.length - 1] = { ...last, linkableExercises: names }
            return copy
        })
    }

    function openExerciseByName(name: string) {
        const found = exercises.find(ex => ex.name.toLowerCase() === name.toLowerCase())
        if (found) setOpenedExercise(found)
    }



    function handleChoice(name: string) {
        setChoices(null)
        if (name === "__manual__") {
            setManualVideoEntry(true)
            send("None of the above", "manual")
        } else {
            send(name, name)
        }
    }

    async function send(text: string, choice: string | null) {
        if (text.trim() === "") return

        // add the user's message, then an empty bot bubble we'll stream into
        setMessages(prev => [
            ...prev,
            { role: "user", content: text, mediaUrl: previewUrl ?? undefined, mediaType: pendingFileType ?? undefined },
            { role: "bot", content: "", pulsing: false },
        ])
        setMessage("")

        const res = await fetch("http://localhost:8000/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                content: text,
                image_path: pendingImage,
                file_type: pendingFileType,
                video_choice: choice,
                user_id: userId,
            }),
        })

        setPendingImage(null)
        setPendingFileType(null)
        setPendingVideoChoice(null)
        setPreviewUrl(null)

        const reader = res.body!.getReader()
        const decoder = new TextDecoder()
        let isStatus = true
        let botText = ""

        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const token = decoder.decode(value)

            if (STATUS_TOKENS.has(token)) {
                updateLastBot(token, true)                 // show "Thinking..." pulsing
            } else if (token.startsWith("CHOICES:")) {
                const [msg, namesStr] = token.replace("CHOICES:", "").split("|")
                setChoices({ message: msg, names: namesStr.split(",") })
                updateLastBot("", false)
            } else if (token.startsWith("EXERCISES:")) {
                updateLastBotExercises(token.replace("EXERCISES:", "").split(","))
            } else {
                if (isStatus) { botText = ""; isStatus = false }  // first real token clears status
                botText += token
                updateLastBot(botText, false)
            }
        }
    }

    function handleSend() {
        let choice = pendingVideoChoice
        if (manualVideoEntry) {
            choice = message
            setManualVideoEntry(false)
        }
        send(message, choice)
    }

    async function handleUpload(e: ChangeEvent<HTMLInputElement>) {
        const file = e.target.files?.[0]
        if (!file) return

        const isVideo = file.type.startsWith("video")
        setPreviewUrl(URL.createObjectURL(file))
        setPendingFileType(isVideo ? "video" : "image")

        const formData = new FormData()
        formData.append("file", file)

        const res = await fetch("http://localhost:8000/upload", { method: "POST", body: formData })
        const data = await res.json()

        setPendingImage(data.file_path)
    }

    function ChoiceButtons({ choices, onPick }: { choices: Choices, onPick: (name: string) => void }) {
        return (
            <div className="bot-message" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div>{choices!.message}</div>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                    {choices!.names.map(name => (
                        <button key={name} className="choice-btn" onClick={() => onPick(name)}>{name}</button>
                    ))}
                    <button className="choice-btn" onClick={() => onPick("__manual__")}>None of the above</button>
                </div>
            </div>
        )
    }

    return (
        <div id="chat-window">
            {messages.map((m, i) => (
                m.role === "user"
                    ? <div key={i} style={{ textAlign: "right" }}>
                        {m.mediaType === "video"
                            ? <video src={m.mediaUrl} controls style={{ maxWidth: "200px", display: "block", marginLeft: "auto" }} />
                            : m.mediaUrl && <img src={m.mediaUrl} style={{ maxWidth: "200px", borderRadius: "10px", display: "block", marginLeft: "auto" }} />
                        }
                        <div className="user-message">{m.content}
                        </div>
                    </div>
                    : <div key={i} className={m.pulsing ? "bot-message pulsing" : "bot-message"}>
                        <ReactMarkdown
                            components={{
                                a: ({ href, children }) => {
                                    const jump = href === "#plans" ? goToPlans : null
                                    return jump
                                        ? <a href={href} onClick={e => { e.preventDefault(); jump() }}>{children}</a>
                                        : <a href={href}>{children}</a>
                                },
                                // make known exercise names tappable wherever they appear
                                // in the model's prose — opens the same ExerciseDetail/
                                // MuscleMap the Exercises tab uses
                                p: ({ children }) => <p>{linkify(children, m.linkableExercises, openExerciseByName)}</p>,
                                li: ({ children }) => <li>{linkify(children, m.linkableExercises, openExerciseByName)}</li>,
                            }}
                        >{m.content}</ReactMarkdown>
                    </div>
            ))}

            {openedExercise && (
                <div
                    onClick={() => setOpenedExercise(null)}
                    style={{
                        position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)",
                        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100
                    }}
                >
                    <div
                        onClick={e => e.stopPropagation()}
                        style={{
                            background: "rgb(255,255,232)", borderRadius: "16px", padding: "20px",
                            width: "min(90vw, 420px)", maxHeight: "80vh", overflowY: "auto",
                            boxShadow: "0 4px 20px rgba(0,0,0,0.2)"
                        }}
                    >
                        <ExerciseDetail ex={openedExercise} onClose={() => setOpenedExercise(null)} />
                    </div>
                </div>
            )}

            {choices && <ChoiceButtons choices={choices} onPick={handleChoice} />}
            <div ref={bottomRef} />

            <div id="input-area">
                {previewUrl && (
                    pendingFileType === "video"
                        ? <video src={previewUrl} style={{
                            position: "absolute", bottom: "100%", left: 0,
                            maxWidth: "60px", maxHeight: "60px", borderRadius: "8px"
                        }} />
                        : <img src={previewUrl} style={{
                            position: "absolute", bottom: "100%", left: 0,
                            maxWidth: "60px", maxHeight: "60px", borderRadius: "8px"
                        }} />
                )}
                <input
                    id="user-input"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter")
                            handleSend()
                    }}
                    autoComplete="off"
                    placeholder=" Ask something!"
                />
                <button id="send-btn" onClick={handleSend}
                    title="Send message">
                    <i className="fa-solid fa-paper-plane"></i>
                </button>

                <label htmlFor="media-upload" title="Attach file">
                    <i className="fa-solid fa-paperclip"></i>
                </label>
                <input
                    type="file"
                    id="media-upload"
                    accept="image/*,video/*"
                    style={{ display: "none" }}
                    onChange={handleUpload}
                />
            </div>
        </div>
    )
}

export default Chat
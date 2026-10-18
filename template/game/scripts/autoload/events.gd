extends Node
## Global signal bus for cross-screen events. Sim classes never use this (they return events instead).

signal screen_changed(path: String)

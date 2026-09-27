"""
navigation  –  Neuro Vision Assist
Clean, modular indoor navigation package.

Modules
-------
graph       : weighted graph definition and dynamic update API
dijkstra    : Dijkstra shortest-path algorithm
navigator   : path → spoken instruction converter
speech      : TTS output (local pyttsx3 + laptop sender)
main        : example entry point
"""

from navigation.graph     import NavGraph, Edge
from navigation.dijkstra  import dijkstra, PathResult
from navigation.navigator import Navigator
from navigation.speech    import Speaker

__all__ = ["NavGraph", "Edge", "dijkstra", "PathResult", "Navigator", "Speaker"]

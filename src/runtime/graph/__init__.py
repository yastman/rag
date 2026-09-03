"""Runtime kernel — configuration for the imperative RAG runtime.

Config, classify, and guard moved out of the graph namespace by #3207
(``src.runtime.config``, ``src.runtime.routing``, ``src.runtime.safety``);
the graph-shaped state schema and compatibility factory were removed in
#3220. The remaining ``nodes`` subtree holds only the unused transcribe
node pending its own cleanup issue.
"""

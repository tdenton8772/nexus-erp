import Config

config :nexus_ui, NexusUiWeb.Endpoint,
  cache_static_manifest: "priv/static/cache_manifest.json",
  server: true

config :logger, level: :info
config :logger, :console, format: "$message\n"

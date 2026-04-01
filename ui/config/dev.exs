import Config

config :nexus_ui, NexusUiWeb.Endpoint,
  http: [ip: {127, 0, 0, 1}, port: 4000],
  check_origin: false,
  code_reloader: true,
  debug_errors: true,
  secret_key_base: "dev-secret-key-base-at-least-64-bytes-change-me-in-production-ok",
  watchers: [
    esbuild: {Esbuild, :install_and_run, [:nexus_ui, ~w(--sourcemap=inline --watch)]},
    tailwind: {Tailwind, :install_and_run, [:nexus_ui, ~w(--watch)]}
  ]

config :nexus_ui, NexusUiWeb.Endpoint,
  live_reload: [
    patterns: [
      ~r"priv/static/(?!uploads/).*(js|css|png|jpeg|jpg|gif|svg)$",
      ~r"lib/nexus_ui_web/(controllers|live|components)/.*(ex|heex)$"
    ]
  ]

config :nexus_ui, :api,
  base_url: System.get_env("NEXUS_API_URL", "http://localhost:8000"),
  timeout: 30_000

config :logger, level: :debug
config :phoenix, :stacktrace_depth, 20
config :phoenix, :plug_init_mode, :runtime

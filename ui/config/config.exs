import Config

config :nexus_ui, NexusUiWeb.Endpoint,
  url: [host: "localhost"],
  adapter: Phoenix.Endpoint.Cowboy2Adapter,
  render_errors: [
    formats: [html: NexusUiWeb.ErrorHTML, json: NexusUiWeb.ErrorJSON],
    layout: false
  ],
  pubsub_server: NexusUi.PubSub,
  live_view: [signing_salt: "nexus_lv_salt_change_me"]

# FastAPI backend base URL
config :nexus_ui, :api,
  base_url: System.get_env("NEXUS_API_URL", "http://localhost:8000"),
  timeout: 30_000

config :nexus_ui, NexusUi.Guardian,
  issuer: "nexus_ui",
  secret_key: System.get_env("GUARDIAN_SECRET", "dev-guardian-secret-change-in-prod")

config :esbuild,
  version: "0.21.5",
  nexus_ui: [
    args: ~w(js/app.js --bundle --target=es2017 --outdir=../priv/static/assets
             --external:/fonts/* --external:/images/*),
    cd: Path.expand("../assets", __DIR__),
    env: %{"NODE_PATH" => Path.expand("../deps", __DIR__)}
  ]

config :tailwind,
  version: "3.4.3",
  nexus_ui: [
    args: ~w(
      --config=tailwind.config.js
      --input=css/app.css
      --output=../priv/static/assets/app.css
    ),
    cd: Path.expand("../assets", __DIR__)
  ]

config :logger, :console,
  format: "$time $metadata[$level] $message\n",
  metadata: [:request_id]

config :phoenix, :json_library, Jason

import_config "#{config_env()}.exs"

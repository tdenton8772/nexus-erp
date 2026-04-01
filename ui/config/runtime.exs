import Config

if config_env() == :prod do
  secret_key_base =
    System.get_env("SECRET_KEY_BASE") ||
      raise "environment variable SECRET_KEY_BASE is missing"

  host = System.get_env("PHX_HOST") || "localhost"
  port = String.to_integer(System.get_env("PORT") || "4000")

  config :nexus_ui, NexusUiWeb.Endpoint,
    http: [
      ip: {0, 0, 0, 0, 0, 0, 0, 0},
      port: port
    ],
    url: [host: host, port: port],
    secret_key_base: secret_key_base,
    check_origin: false

  config :nexus_ui, :api,
    base_url: System.get_env("NEXUS_API_URL") || raise("NEXUS_API_URL is missing"),
    timeout: String.to_integer(System.get_env("API_TIMEOUT") || "30000")

  config :nexus_ui, NexusUi.Guardian,
    secret_key: System.get_env("GUARDIAN_SECRET") || raise("GUARDIAN_SECRET is missing")
end

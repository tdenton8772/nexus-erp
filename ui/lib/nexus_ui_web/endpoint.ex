defmodule NexusUiWeb.Endpoint do
  use Phoenix.Endpoint, otp_app: :nexus_ui

  @session_options [
    store: :cookie,
    key: "_nexus_ui_key",
    signing_salt: "nexus_signing_salt",
    same_site: "Lax"
  ]

  socket "/live", Phoenix.LiveView.Socket,
    websocket: [connect_info: [session: @session_options]],
    longpoll: [connect_info: [session: @session_options]]

  # Serve assets from priv/static
  plug Plug.Static,
    at: "/",
    from: :nexus_ui,
    gzip: false,
    only: NexusUiWeb.static_paths()

  if code_reloading? do
    plug Phoenix.CodeReloader
    plug Phoenix.Ecto.CheckRepoStatus, otp_app: :nexus_ui
  end

  plug Phoenix.LiveDashboard.RequestLogger,
    param_key: "request_logger",
    cookie_key: "request_logger"

  plug Plug.RequestId
  plug Plug.Telemetry, event_prefix: [:phoenix, :endpoint]

  plug Plug.Parsers,
    parsers: [:urlencoded, :multipart, :json],
    pass: ["*/*"],
    json_decoder: Phoenix.json_library()

  plug Plug.MethodOverride
  plug Plug.Head
  plug Plug.Session, @session_options
  plug NexusUiWeb.Router
end

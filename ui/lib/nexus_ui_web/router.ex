defmodule NexusUiWeb.Router do
  use NexusUiWeb, :router

  pipeline :browser do
    plug :accepts, ["html"]
    plug :fetch_session
    plug :fetch_live_flash
    plug :put_root_layout, html: {NexusUiWeb.Layouts, :root}
    plug :protect_from_forgery
    plug :put_secure_browser_headers
  end

  pipeline :api do
    plug :accepts, ["json"]
  end

  # ── Public routes ────────────────────────────────────────────────────────────
  scope "/", NexusUiWeb do
    pipe_through :browser

    live "/", DashboardLive, :index
    live "/connectors", ConnectorsLive, :index
    live "/connectors/new", ConnectorsLive, :new
    live "/connectors/:id", ConnectorsLive, :show
    live "/connectors/:id/edit", ConnectorsLive, :edit

    live "/pipelines", PipelinesLive, :index
    live "/pipelines/new", PipelinesLive, :new
    live "/pipelines/:id", PipelineDetailLive, :show
    live "/pipelines/:id/mappings", MappingEditorLive, :show
    live "/pipelines/:id/transformation", TransformationLive, :show

    live "/schemas", SchemaRegistryLive, :index
    live "/schemas/:connector_id", SchemaRegistryLive, :connector
    live "/schemas/:connector_id/:entity", SchemaDiffLive, :show

    live "/agent/proposals", AgentProposalsLive, :index
    live "/agent/proposals/:id", AgentProposalDetailLive, :show

    live "/monitoring", MonitoringLive, :index
    live "/monitoring/:pipeline_id", PipelineMonitorLive, :show
  end

  # ── LiveDashboard (dev only) ─────────────────────────────────────────────────
  if Application.compile_env(:nexus_ui, :dev_routes) do
    import Phoenix.LiveDashboard.Router

    scope "/dev" do
      pipe_through :browser
      live_dashboard "/dashboard", metrics: NexusUiWeb.Telemetry
    end
  end
end

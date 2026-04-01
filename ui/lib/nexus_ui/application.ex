defmodule NexusUi.Application do
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      NexusUiWeb.Telemetry,
      {Phoenix.PubSub, name: NexusUi.PubSub},
      NexusUiWeb.Endpoint
    ]

    opts = [strategy: :one_for_one, name: NexusUi.Supervisor]
    Supervisor.start_link(children, opts)
  end

  @impl true
  def config_change(changed, _new, removed) do
    NexusUiWeb.Endpoint.config_change(changed, removed)
    :ok
  end
end

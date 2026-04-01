defmodule NexusUi.MixProject do
  use Mix.Project

  def project do
    [
      app: :nexus_ui,
      version: "0.1.0",
      elixir: "~> 1.16",
      elixirc_paths: elixirc_paths(Mix.env()),
      start_permanent: Mix.env() == :prod,
      aliases: aliases(),
      deps: deps()
    ]
  end

  def application do
    [
      mod: {NexusUi.Application, []},
      extra_applications: [:logger, :runtime_tools]
    ]
  end

  defp elixirc_paths(:test), do: ["lib", "test/support"]
  defp elixirc_paths(_), do: ["lib"]

  defp deps do
    [
      # Phoenix core
      {:phoenix, "~> 1.7.14"},
      {:phoenix_html, "~> 4.1"},
      {:phoenix_live_reload, "~> 1.5", only: :dev},
      {:phoenix_live_view, "~> 0.20.17"},
      {:phoenix_live_dashboard, "~> 0.8.4"},

      # HTTP client for FastAPI calls
      {:req, "~> 0.5.0"},

      # JSON
      {:jason, "~> 1.4"},

      # Server-Sent Events / WebSocket forwarding
      {:plug_cowboy, "~> 2.7"},

      # Auth (simple token-based to start)
      {:guardian, "~> 2.3"},

      # Asset pipeline
      {:esbuild, "~> 0.8", runtime: Mix.env() == :dev},
      {:tailwind, "~> 0.2", runtime: Mix.env() == :dev},

      # Telemetry
      {:telemetry_metrics, "~> 1.0"},
      {:telemetry_poller, "~> 1.1"},

      # Test
      {:floki, ">= 0.36.0", only: :test}
    ]
  end

  defp aliases do
    [
      setup: ["deps.get", "assets.setup", "assets.build"],
      "assets.setup": ["tailwind.install --if-missing", "esbuild.install --if-missing"],
      "assets.build": ["tailwind nexus_ui", "esbuild nexus_ui"],
      "assets.deploy": [
        "tailwind nexus_ui --minify",
        "esbuild nexus_ui --minify",
        "phx.digest"
      ]
    ]
  end
end

defmodule NexusUiWeb.Layouts do
  use NexusUiWeb, :html

  use Phoenix.VerifiedRoutes,
    endpoint: NexusUiWeb.Endpoint,
    router: NexusUiWeb.Router,
    statics: NexusUiWeb.static_paths()

  import NexusUiWeb.NavComponent, only: [nav_item: 1]

  embed_templates "layouts/*"
end

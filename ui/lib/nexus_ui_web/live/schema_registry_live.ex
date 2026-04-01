defmodule NexusUiWeb.SchemaRegistryLive do
  @moduledoc """
  Schema Registry — browse discovered schemas per connector and entity.
  """
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @impl true
  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:page_title, "Schema Registry")
     |> assign(:connectors, [])
     |> assign(:selected_connector, nil)
     |> assign(:schemas, [])
     |> load_connectors()}
  end

  @impl true
  def handle_params(params, _url, socket) do
    {:noreply, apply_action(socket, socket.assigns.live_action, params)}
  end

  defp apply_action(socket, :index, _params), do: socket

  defp apply_action(socket, :connector, %{"connector_id" => connector_id}) do
    connector =
      Enum.find(socket.assigns.connectors, fn c -> c["id"] == connector_id end) ||
        case ApiClient.get_connector(connector_id) do
          {:ok, c} -> c
          _ -> %{"id" => connector_id, "display_name" => connector_id}
        end

    schemas =
      case ApiClient.list_schemas(connector_id) do
        {:ok, data} -> data["items"] || data || []
        _ -> []
      end

    socket
    |> assign(:selected_connector, connector)
    |> assign(:schemas, schemas)
  end

  defp load_connectors(socket) do
    connectors =
      case ApiClient.list_connectors() do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    assign(socket, :connectors, connectors)
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-6">
      <h1 class="text-2xl font-bold text-gray-900">Schema Registry</h1>

      <div class="grid grid-cols-4 gap-6">
        <%!-- Connector list --%>
        <div class="col-span-1">
          <div class="bg-white rounded-lg shadow overflow-hidden">
            <div class="px-4 py-3 border-b bg-gray-50">
              <h2 class="text-sm font-semibold text-gray-700">Connectors</h2>
            </div>
            <div class="divide-y divide-gray-100">
              <%= if @connectors == [] do %>
                <div class="px-4 py-6 text-center text-sm text-gray-400">
                  No connectors configured.
                  <.link navigate="/connectors/new" class="text-blue-600 hover:underline block mt-1">
                    Add one →
                  </.link>
                </div>
              <% end %>
              <%= for c <- @connectors do %>
                <.link
                  patch={"/schemas/#{c["id"]}"}
                  class={"block px-4 py-3 text-sm hover:bg-gray-50 transition " <>
                    if @selected_connector && @selected_connector["id"] == c["id"],
                      do: "bg-blue-50 border-l-2 border-blue-500", else: ""}>
                  <p class="font-medium text-gray-900"><%= c["display_name"] %></p>
                  <p class="text-xs text-gray-400 font-mono mt-0.5"><%= c["system_name"] %></p>
                </.link>
              <% end %>
            </div>
          </div>
        </div>

        <%!-- Schema list --%>
        <div class="col-span-3">
          <%= if is_nil(@selected_connector) do %>
            <div class="bg-white rounded-lg shadow flex items-center justify-center h-64 text-gray-400">
              <div class="text-center">
                <p class="text-4xl mb-2">📋</p>
                <p>Select a connector to view its schemas</p>
              </div>
            </div>
          <% else %>
            <div class="bg-white rounded-lg shadow overflow-hidden">
              <div class="px-4 py-3 border-b bg-gray-50 flex justify-between items-center">
                <h2 class="text-sm font-semibold text-gray-700">
                  Schemas — <%= @selected_connector["display_name"] %>
                </h2>
                <span class="text-xs text-gray-400"><%= length(@schemas) %> entities</span>
              </div>

              <%= if @schemas == [] do %>
                <div class="px-4 py-12 text-center text-gray-400">
                  <p class="text-3xl mb-2">🔍</p>
                  <p class="font-medium">No schemas discovered yet</p>
                  <p class="text-sm mt-1">
                    Go to
                    <.link navigate="/connectors" class="text-blue-600 hover:underline">Connectors</.link>
                    and run "Discover Schemas".
                  </p>
                </div>
              <% end %>

              <table class="w-full text-sm">
                <%= if @schemas != [] do %>
                  <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
                    <tr>
                      <th class="px-4 py-2 text-left">Entity</th>
                      <th class="px-4 py-2 text-left">Version</th>
                      <th class="px-4 py-2 text-left">Fields</th>
                      <th class="px-4 py-2 text-left">Discovered</th>
                      <th class="px-4 py-2 text-left">Status</th>
                      <th class="px-4 py-2"></th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-100">
                    <%= for schema <- @schemas do %>
                      <tr class="hover:bg-gray-50">
                        <td class="px-4 py-3 font-medium font-mono text-gray-900">
                          <%= schema["entity_name"] %>
                        </td>
                        <td class="px-4 py-3 text-gray-500">
                          v<%= schema["version"] %>
                        </td>
                        <td class="px-4 py-3 text-gray-500">
                          <%= length(schema["schema_json"]["fields"] || []) %> fields
                        </td>
                        <td class="px-4 py-3 text-gray-400 text-xs">
                          <%= format_date(schema["discovered_at"]) %>
                        </td>
                        <td class="px-4 py-3">
                          <span class={"px-2 py-0.5 rounded text-xs font-medium " <>
                            if schema["is_current"], do: "bg-green-100 text-green-700",
                                                    else: "bg-gray-100 text-gray-500"}>
                            <%= if schema["is_current"], do: "current", else: "archived" %>
                          </span>
                        </td>
                        <td class="px-4 py-3 text-right">
                          <.link
                            navigate={"/schemas/#{@selected_connector["id"]}/#{schema["entity_name"]}"}
                            class="text-blue-600 hover:underline text-xs">
                            View diff →
                          </.link>
                        </td>
                      </tr>
                    <% end %>
                  </tbody>
                <% end %>
              </table>
            </div>
          <% end %>
        </div>
      </div>
    </div>
    """
  end

  defp format_date(nil), do: "—"
  defp format_date(ts) when is_binary(ts), do: String.slice(ts, 0, 10)
  defp format_date(_), do: "—"
end

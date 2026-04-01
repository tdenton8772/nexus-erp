defmodule NexusUiWeb.SchemaDiffLive do
  @moduledoc """
  Schema diff view — shows field-level changes between schema versions for an entity.
  """
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @impl true
  def mount(%{"connector_id" => connector_id, "entity" => entity}, _session, socket) do
    versions =
      case ApiClient.get_schema(connector_id, entity) do
        {:ok, schema} -> [schema]
        _ -> []
      end

    diffs =
      case ApiClient.list_schema_diffs(connector_id, entity) do
        {:ok, data} -> data["items"] || data || []
        _ -> []
      end

    current = Enum.find(versions, & &1["is_current"])

    {:ok,
     socket
     |> assign(:page_title, "Schema Diff — #{entity}")
     |> assign(:connector_id, connector_id)
     |> assign(:entity, entity)
     |> assign(:versions, versions)
     |> assign(:diffs, diffs)
     |> assign(:current, current)}
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-6">
      <div class="flex items-center gap-2 text-sm text-gray-500">
        <.link navigate="/schemas" class="hover:text-blue-600">Schema Registry</.link>
        <span>›</span>
        <.link navigate={"/schemas/#{@connector_id}"} class="hover:text-blue-600">
          <%= @connector_id %>
        </.link>
        <span>›</span>
        <span class="text-gray-900 font-medium"><%= @entity %></span>
      </div>

      <h1 class="text-2xl font-bold text-gray-900"><%= @entity %> — Schema History</h1>

      <%!-- Current schema --%>
      <%= if @current do %>
        <div class="bg-white rounded-lg shadow overflow-hidden">
          <div class="px-4 py-3 border-b bg-gray-50 flex justify-between items-center">
            <h2 class="font-semibold text-gray-700">
              Current Schema
              <span class="ml-2 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                v<%= @current["version"] %>
              </span>
            </h2>
            <span class="text-xs text-gray-400">
              Discovered <%= format_date(@current["discovered_at"]) %>
            </span>
          </div>
          <div class="p-4">
            <table class="w-full text-sm">
              <thead class="text-gray-500 text-xs uppercase border-b">
                <tr>
                  <th class="pb-2 text-left">Field</th>
                  <th class="pb-2 text-left">Type</th>
                  <th class="pb-2 text-left">Required</th>
                  <th class="pb-2 text-left">Description</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-50">
                <%= for field <- @current["schema_json"]["fields"] || [] do %>
                  <tr class="hover:bg-gray-50">
                    <td class="py-1.5 font-mono text-gray-900"><%= field["name"] %></td>
                    <td class="py-1.5 text-gray-500 font-mono text-xs"><%= field["data_type"] %></td>
                    <td class="py-1.5">
                      <%= if field["required"] do %>
                        <span class="text-red-500 text-xs">required</span>
                      <% else %>
                        <span class="text-gray-300 text-xs">optional</span>
                      <% end %>
                    </td>
                    <td class="py-1.5 text-gray-400 text-xs"><%= field["description"] %></td>
                  </tr>
                <% end %>
              </tbody>
            </table>
          </div>
        </div>
      <% end %>

      <%!-- Diffs --%>
      <%= if @diffs != [] do %>
        <div class="bg-white rounded-lg shadow overflow-hidden">
          <div class="px-4 py-3 border-b bg-gray-50">
            <h2 class="font-semibold text-gray-700">Schema Changes</h2>
          </div>
          <div class="divide-y divide-gray-100">
            <%= for diff <- @diffs do %>
              <div class="p-4 space-y-2">
                <div class="flex justify-between items-center">
                  <span class="text-sm font-medium text-gray-700">
                    v<%= diff["from_version"] %> → v<%= diff["to_version"] %>
                  </span>
                  <span class="text-xs text-gray-400"><%= format_date(diff["detected_at"]) %></span>
                </div>
                <div class="space-y-1">
                  <%= for change <- diff["diff_json"]["changes"] || [] do %>
                    <div class={"flex items-center gap-2 px-3 py-1.5 rounded text-xs font-mono " <>
                      change_class(change["type"])}>
                      <span class="font-bold"><%= change_icon(change["type"]) %></span>
                      <span><%= change["field"] %></span>
                      <%= if change["from_type"] && change["to_type"] do %>
                        <span class="text-gray-500">
                          <%= change["from_type"] %> → <%= change["to_type"] %>
                        </span>
                      <% end %>
                    </div>
                  <% end %>
                </div>
              </div>
            <% end %>
          </div>
        </div>
      <% else %>
        <div class="bg-white rounded-lg shadow px-4 py-8 text-center text-gray-400">
          <p>No schema changes detected yet.</p>
        </div>
      <% end %>
    </div>
    """
  end

  defp format_date(nil), do: "—"
  defp format_date(ts) when is_binary(ts), do: String.slice(ts, 0, 10)
  defp format_date(_), do: "—"

  defp change_class("added"), do: "bg-green-50 text-green-800"
  defp change_class("removed"), do: "bg-red-50 text-red-800"
  defp change_class("modified"), do: "bg-yellow-50 text-yellow-800"
  defp change_class(_), do: "bg-gray-50 text-gray-700"

  defp change_icon("added"), do: "+"
  defp change_icon("removed"), do: "-"
  defp change_icon("modified"), do: "~"
  defp change_icon(_), do: "?"
end

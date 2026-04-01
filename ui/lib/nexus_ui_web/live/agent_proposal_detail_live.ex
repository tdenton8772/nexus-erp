defmodule NexusUiWeb.AgentProposalDetailLive do
  @moduledoc "Detailed view of a single agent proposal with full diff and review actions."
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @impl true
  def mount(%{"id" => id}, _session, socket) do
    case ApiClient.get_proposal(id) do
      {:ok, proposal} ->
        {:ok,
         socket
         |> assign(:page_title, "Proposal — #{proposal["trigger_type"]}")
         |> assign(:proposal, proposal)
         |> assign(:feedback, "")}

      {:error, _} ->
        {:ok,
         socket
         |> put_flash(:error, "Proposal not found")
         |> push_navigate(to: "/agent/proposals")}
    end
  end

  @impl true
  def handle_event("set_feedback", %{"value" => feedback}, socket) do
    {:noreply, assign(socket, :feedback, feedback)}
  end

  def handle_event("approve", %{"id" => id}, socket) do
    case ApiClient.review_proposal(id, "approve") do
      {:ok, _} ->
        {:noreply,
         socket
         |> put_flash(:info, "Proposal approved and mappings applied")
         |> push_navigate(to: "/agent/proposals")}
      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("reject", %{"id" => id}, socket) do
    case ApiClient.review_proposal(id, "reject") do
      {:ok, _} ->
        {:noreply,
         socket
         |> put_flash(:info, "Proposal rejected")
         |> push_navigate(to: "/agent/proposals")}
      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("modify", %{"id" => id}, socket) do
    case ApiClient.review_proposal(id, "modify", socket.assigns.feedback) do
      {:ok, _} ->
        {:noreply,
         socket
         |> put_flash(:info, "Feedback sent — agent will revise the proposal")
         |> push_navigate(to: "/agent/proposals")}
      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-6">
      <div class="flex items-center gap-2 text-sm text-gray-500">
        <.link navigate="/agent/proposals" class="hover:text-blue-600">Agent Proposals</.link>
        <span>›</span>
        <span class="text-gray-900 font-medium"><%= @proposal["trigger_type"] %></span>
      </div>

      <div class="flex justify-between items-start">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">
            <%= String.replace(@proposal["trigger_type"] || "proposal", "_", " ") |> String.capitalize() %>
          </h1>
          <p class="text-sm text-gray-500 mt-1">
            Pipeline: <span class="font-mono"><%= @proposal["pipeline_id"] %></span>
            · Created <%= format_date(@proposal["created_at"]) %>
          </p>
        </div>
        <span class={"px-3 py-1 rounded text-sm font-medium " <> status_class(@proposal["status"])}>
          <%= @proposal["status"] %>
        </span>
      </div>

      <%!-- Proposed mappings --%>
      <div class="bg-white rounded-lg shadow overflow-hidden">
        <div class="px-4 py-3 border-b bg-gray-50">
          <h2 class="font-semibold text-gray-700">
            Proposed Field Mappings
            (<%= length(@proposal["proposal_json"]["field_mappings"] || []) %>)
          </h2>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="px-4 py-2 text-left">Source Field</th>
              <th class="px-4 py-2 text-left">Transform</th>
              <th class="px-4 py-2 text-left">Target Field</th>
              <th class="px-4 py-2 text-left">Confidence</th>
              <th class="px-4 py-2 text-left">Note</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <%= for m <- @proposal["proposal_json"]["field_mappings"] || [] do %>
              <tr class="hover:bg-gray-50">
                <td class="px-4 py-2 font-mono text-blue-700"><%= m["source_field"] %></td>
                <td class="px-4 py-2">
                  <span class="bg-gray-100 px-2 py-0.5 rounded text-xs font-mono">
                    <%= m["transform"] %>
                  </span>
                </td>
                <td class="px-4 py-2 font-mono text-green-700"><%= m["target_field"] %></td>
                <td class="px-4 py-2">
                  <div class="flex items-center gap-2">
                    <div class="w-20 bg-gray-200 rounded-full h-1.5">
                      <div class={"h-1.5 rounded-full " <> confidence_color(m["confidence"])}
                           style={"width: #{round((m["confidence"] || 0) * 100)}%"}></div>
                    </div>
                    <span class="text-xs text-gray-500">
                      <%= round((m["confidence"] || 0) * 100) %>%
                    </span>
                  </div>
                </td>
                <td class="px-4 py-2 text-gray-500 text-xs"><%= m["note"] %></td>
              </tr>
            <% end %>
          </tbody>
        </table>
      </div>

      <%!-- Unmapped fields --%>
      <%= if (unmapped = @proposal["proposal_json"]["unmapped_source_fields"] || []) != [] do %>
        <div class="bg-red-50 border border-red-200 rounded-lg p-4">
          <h3 class="text-sm font-semibold text-red-700 mb-1">Unmapped Source Fields</h3>
          <div class="flex flex-wrap gap-2">
            <%= for f <- unmapped do %>
              <span class="bg-red-100 text-red-700 px-2 py-0.5 rounded font-mono text-xs">
                <%= f %>
              </span>
            <% end %>
          </div>
        </div>
      <% end %>

      <%!-- Review panel --%>
      <%= if @proposal["status"] == "pending_review" do %>
        <div class="bg-white rounded-lg shadow p-6 space-y-4">
          <h2 class="font-semibold text-gray-700">Review Decision</h2>
          <div>
            <label class="text-sm text-gray-600">
              Feedback for agent (optional — leave blank to approve/reject as-is)
            </label>
            <textarea
              phx-blur="set_feedback"
              phx-value-value={@feedback}
              rows="3"
              placeholder="e.g. 'The customer_name → name mapping is correct but use lowercase transform instead'"
              class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            ><%= @feedback %></textarea>
          </div>
          <div class="flex gap-3">
            <button phx-click="approve" phx-value-id={@proposal["id"]}
                    class="btn-primary">
              ✓ Approve & Apply Mappings
            </button>
            <%= if @feedback != "" do %>
              <button phx-click="modify" phx-value-id={@proposal["id"]}
                      class="btn-secondary">
                ↩ Send Feedback for Revision
              </button>
            <% end %>
            <button phx-click="reject" phx-value-id={@proposal["id"]}
                    class="text-red-500 hover:text-red-700 text-sm px-4">
              ✕ Reject
            </button>
          </div>
        </div>
      <% end %>
    </div>
    """
  end

  defp status_class("pending_review"), do: "bg-yellow-100 text-yellow-800"
  defp status_class("approved"), do: "bg-green-100 text-green-800"
  defp status_class("rejected"), do: "bg-red-100 text-red-800"
  defp status_class(_), do: "bg-gray-100 text-gray-700"

  defp confidence_color(score) when is_number(score) and score >= 0.9, do: "bg-green-400"
  defp confidence_color(score) when is_number(score) and score >= 0.7, do: "bg-yellow-400"
  defp confidence_color(_), do: "bg-red-400"

  defp format_date(nil), do: "—"
  defp format_date(ts) when is_binary(ts), do: String.slice(ts, 0, 16) |> String.replace("T", " ")
  defp format_date(_), do: "—"
end

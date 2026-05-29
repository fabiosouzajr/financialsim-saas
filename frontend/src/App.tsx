import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Health from "./routes/Health";
import Index from "./routes/Index";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/healthz" element={<Health />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

import {
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";

import { Layout } from "./routes/_layout";
import { HomeRoute } from "./routes/index";
import { LiveRoute } from "./routes/session.$id.live";
import { ReviewRoute } from "./routes/session.$id.review";

const rootRoute = createRootRoute({ component: Layout });
const home = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomeRoute,
});
const live = createRoute({
  getParentRoute: () => rootRoute,
  path: "/session/$id/live",
  component: LiveRoute,
});
const review = createRoute({
  getParentRoute: () => rootRoute,
  path: "/session/$id/review",
  component: ReviewRoute,
});

const router = createRouter({
  routeTree: rootRoute.addChildren([home, live, review]),
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

export function App() {
  return <RouterProvider router={router} />;
}

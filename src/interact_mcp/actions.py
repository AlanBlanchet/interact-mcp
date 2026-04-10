from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from playwright.async_api import Page


class Action(BaseModel):
    mutates: ClassVar[bool] = True
    wait: str | None = None


class ObservationAction(Action):
    mutates: ClassVar[bool] = False


class ClickAction(Action):
    type: Literal["click"] = "click"
    selector: str | None = None
    x: int | None = None
    y: int | None = None

    @model_validator(mode="after")
    def _require_target(self):
        if not self.selector and (self.x is None or self.y is None):
            raise ValueError("Provide selector or both x and y")
        return self

    async def execute(self, page: Page):
        if self.selector:
            await page.click(self.selector)
        else:
            await page.mouse.click(self.x, self.y)


class TypeTextAction(Action):
    type: Literal["type_text"] = "type_text"
    selector: str
    text: str
    clear_first: bool = True

    async def execute(self, page: Page):
        if self.clear_first:
            await page.fill(self.selector, self.text)
        else:
            await page.type(self.selector, self.text)


class ScrollAction(Action):
    DELTA: ClassVar[dict[str, tuple[int, int]]] = {
        "down": (0, 300),
        "up": (0, -300),
        "right": (300, 0),
        "left": (-300, 0),
    }
    type: Literal["scroll"] = "scroll"
    direction: Literal["down", "up", "left", "right"] = "down"
    amount: int = 3

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, v: int):
        if v <= 0:
            raise ValueError("amount must be > 0")
        return v

    async def execute(self, page: Page):
        dx, dy = self.DELTA[self.direction]
        for _ in range(self.amount):
            await page.mouse.wheel(dx, dy)


class DragAction(Action):
    type: Literal["drag"] = "drag"
    from_x: int
    from_y: int
    to_x: int
    to_y: int

    async def execute(self, page: Page):
        await page.mouse.move(self.from_x, self.from_y)
        await page.mouse.down()
        await page.mouse.move(self.to_x, self.to_y)
        await page.mouse.up()


class NavigateAction(Action):
    type: Literal["navigate"] = "navigate"
    url: str

    async def execute(self, page: Page):
        await page.goto(self.url)


class EvaluateJsAction(Action):
    type: Literal["evaluate_js"] = "evaluate_js"
    script: str

    async def execute(self, page: Page):
        return await page.evaluate(self.script)


class ScreenshotAction(ObservationAction):
    type: Literal["screenshot"] = "screenshot"
    scope: str | None = None
    query: str | None = None


class WaitForAction(ObservationAction):
    type: Literal["wait_for"] = "wait_for"
    selector: str
    state: Literal["visible", "hidden", "attached", "detached"] = "visible"
    timeout: int = 10000

    @field_validator("timeout")
    @classmethod
    def _positive_timeout(cls, v: int):
        if v <= 0:
            raise ValueError("timeout must be > 0")
        return v

    async def execute(self, page: Page):
        await page.wait_for_selector(
            self.selector, state=self.state, timeout=self.timeout
        )
        return f"'{self.selector}' is {self.state}"


class ListClickableAction(ObservationAction):
    type: Literal["list_clickable"] = "list_clickable"
    scope: str | None = None

    async def execute(self, page: Page):
        elements = await page.evaluate(
            """(scopeSelector) => {
            const root = scopeSelector ? document.querySelector(scopeSelector) : document;
            if (!root) return [];
            const items = root.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="link"], [role="tab"], [onclick]');
            return Array.from(items).slice(0, 100).map((el, i) => {
                const tag = el.tagName.toLowerCase();
                const text = (el.textContent || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 80);
                const type = el.type || '';
                const href = el.href || '';

                let selector = '';
                if (el.id) selector = '#' + el.id;
                else if (el.getAttribute('data-testid')) selector = `[data-testid="${el.getAttribute('data-testid')}"]`;
                else if (el.name) selector = `${tag}[name="${el.name}"]`;
                else if (text && tag === 'button') selector = `button:has-text("${text.slice(0, 30)}")`;
                else if (text && tag === 'a') selector = `a:has-text("${text.slice(0, 30)}")`;
                else {
                    const classes = Array.from(el.classList).slice(0, 2).join('.');
                    selector = classes ? `${tag}.${classes}` : `${tag}:nth-of-type(${i + 1})`;
                }

                return { tag, selector, text, type, href };
            });
        }""",
            self.scope,
        )

        if not elements:
            return "No interactive elements found." + (
                f" (scoped to '{self.scope}')" if self.scope else ""
            )

        lines = []
        for el in elements:
            parts = [el["tag"]]
            if el["type"]:
                parts.append(f"type={el['type']}")
            if el["text"]:
                parts.append(f'"{el["text"]}"')
            if el["href"]:
                parts.append(f"-> {el['href'][:60]}")
            lines.append(f"  {el['selector']}  [{' | '.join(parts)}]")

        return "\n".join(lines)


AnyAction = Annotated[
    ClickAction
    | TypeTextAction
    | ScrollAction
    | DragAction
    | NavigateAction
    | EvaluateJsAction
    | ScreenshotAction
    | WaitForAction
    | ListClickableAction,
    Field(discriminator="type"),
]
